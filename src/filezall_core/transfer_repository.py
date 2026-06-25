from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Final

from filezall_core.models import (
    ConflictPolicy,
    Direction,
    Protocol,
    TransferItem,
    TransferStatus,
    TransferTask,
)


_UNCHANGED: Final = object()


class TransferRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def save_task(self, task: TransferTask, items: list[TransferItem]) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """
                insert into transfer_tasks (
                    id, server_id, direction, source_path, destination_path,
                    protocol, conflict_policy, status, created_time, updated_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
                on conflict(id) do update set
                    server_id = excluded.server_id,
                    direction = excluded.direction,
                    source_path = excluded.source_path,
                    destination_path = excluded.destination_path,
                    protocol = excluded.protocol,
                    conflict_policy = excluded.conflict_policy,
                    status = excluded.status,
                    created_time = excluded.created_time,
                    updated_at = current_timestamp
                """,
                self._task_to_row(task),
            )
            connection.executemany(
                """
                insert into transfer_items (
                    id, task_id, server_id, direction, source_path, destination_path,
                    temporary_path, size_bytes, modified_time, checksum,
                    bytes_transferred, status, retry_count, last_error, protocol,
                    updated_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
                on conflict(id) do update set
                    task_id = excluded.task_id,
                    server_id = excluded.server_id,
                    direction = excluded.direction,
                    source_path = excluded.source_path,
                    destination_path = excluded.destination_path,
                    temporary_path = excluded.temporary_path,
                    size_bytes = excluded.size_bytes,
                    modified_time = excluded.modified_time,
                    checksum = excluded.checksum,
                    bytes_transferred = excluded.bytes_transferred,
                    status = excluded.status,
                    retry_count = excluded.retry_count,
                    last_error = excluded.last_error,
                    protocol = excluded.protocol,
                    updated_at = current_timestamp
                """,
                [self._item_to_row(item) for item in items],
            )
            connection.commit()

    def get_task(self, task_id: str) -> TransferTask | None:
        with sqlite3.connect(self._database_path) as connection:
            row = connection.execute(
                """
                select id, server_id, direction, source_path, destination_path,
                       protocol, conflict_policy, status, created_time
                from transfer_tasks
                where id = ?
                """,
                (task_id,),
            ).fetchone()
        return self._task_from_row(row) if row else None

    def get_item(self, item_id: str) -> TransferItem | None:
        with sqlite3.connect(self._database_path) as connection:
            row = connection.execute(
                self._item_select_sql("where id = ?"),
                (item_id,),
            ).fetchone()
        return self._item_from_row(row) if row else None

    def list_items(self, task_id: str) -> list[TransferItem]:
        with sqlite3.connect(self._database_path) as connection:
            rows = connection.execute(
                self._item_select_sql("where task_id = ? order by created_at, id"),
                (task_id,),
            ).fetchall()
        return [self._item_from_row(row) for row in rows]

    def list_all_items(self, status: TransferStatus | None = None) -> list[TransferItem]:
        where_clause = "order by created_at, id"
        params: tuple[object, ...] = ()
        if status is not None:
            where_clause = "where status = ? order by created_at, id"
            params = (status.value,)
        with sqlite3.connect(self._database_path) as connection:
            rows = connection.execute(self._item_select_sql(where_clause), params).fetchall()
        return [self._item_from_row(row) for row in rows]

    def list_recoverable_items(self) -> list[TransferItem]:
        with sqlite3.connect(self._database_path) as connection:
            rows = connection.execute(
                self._item_select_sql(
                    """
                    where status not in (?, ?)
                    order by created_at, id
                    """
                ),
                (TransferStatus.COMPLETED.value, TransferStatus.CANCELED.value),
            ).fetchall()
        return [self._item_from_row(row) for row in rows]

    def update_item_progress(
        self,
        item_id: str,
        bytes_transferred: int,
        status: TransferStatus,
        last_error: str | None = None,
    ) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """
                update transfer_items
                set bytes_transferred = ?,
                    status = ?,
                    last_error = ?,
                    updated_at = current_timestamp
                where id = ?
                """,
                (bytes_transferred, status.value, last_error, item_id),
            )
            connection.commit()

    def update_item_state(
        self,
        item_id: str,
        status: TransferStatus,
        last_error: str | None | object = _UNCHANGED,
        retry_count: int | None = None,
    ) -> None:
        item = self.get_item(item_id)
        if item is None:
            return
        next_error = item.last_error if last_error is _UNCHANGED else last_error
        next_retry_count = item.retry_count if retry_count is None else retry_count
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """
                update transfer_items
                set status = ?,
                    last_error = ?,
                    retry_count = ?,
                    updated_at = current_timestamp
                where id = ?
                """,
                (status.value, next_error, next_retry_count, item_id),
            )
            connection.commit()

    @staticmethod
    def _item_select_sql(where_clause: str) -> str:
        return f"""
            select id, task_id, server_id, direction, source_path, destination_path,
                   temporary_path, size_bytes, modified_time, checksum,
                   bytes_transferred, status, retry_count, last_error, protocol
            from transfer_items
            {where_clause}
        """

    @staticmethod
    def _task_to_row(task: TransferTask) -> tuple[object, ...]:
        return (
            task.id,
            task.server_id,
            task.direction.value,
            str(task.source_path),
            str(task.destination_path),
            task.protocol.value,
            task.conflict_policy.value,
            task.status.value,
            task.created_time.isoformat(),
        )

    @staticmethod
    def _item_to_row(item: TransferItem) -> tuple[object, ...]:
        return (
            item.id,
            item.task_id,
            item.server_id,
            item.direction.value,
            str(item.source_path),
            str(item.destination_path),
            str(item.temporary_path),
            item.size_bytes,
            item.modified_time.isoformat() if item.modified_time else None,
            item.checksum,
            item.bytes_transferred,
            item.status.value,
            item.retry_count,
            item.last_error,
            item.protocol.value,
        )

    @staticmethod
    def _task_from_row(row: sqlite3.Row | tuple[object, ...]) -> TransferTask:
        direction = Direction(str(row[2]))
        return TransferTask(
            id=str(row[0]),
            server_id=str(row[1]),
            direction=direction,
            source_path=_source_path(direction, str(row[3])),
            destination_path=_destination_path(direction, str(row[4])),
            protocol=Protocol(str(row[5])),
            conflict_policy=ConflictPolicy(str(row[6])),
            status=TransferStatus(str(row[7])),
            created_time=datetime.fromisoformat(str(row[8])),
        )

    @staticmethod
    def _item_from_row(row: sqlite3.Row | tuple[object, ...]) -> TransferItem:
        direction = Direction(str(row[3]))
        return TransferItem(
            id=str(row[0]),
            task_id=str(row[1]),
            server_id=str(row[2]),
            direction=direction,
            source_path=_source_path(direction, str(row[4])),
            destination_path=_destination_path(direction, str(row[5])),
            temporary_path=_temporary_path(direction, str(row[6])),
            size_bytes=int(row[7]),
            modified_time=datetime.fromisoformat(str(row[8])) if row[8] else None,
            checksum=str(row[9]) if row[9] else None,
            bytes_transferred=int(row[10]),
            status=TransferStatus(str(row[11])),
            retry_count=int(row[12]),
            last_error=str(row[13]) if row[13] else None,
            protocol=Protocol(str(row[14])),
        )


def _source_path(direction: Direction, value: str) -> Path | PurePosixPath:
    return Path(value) if direction is Direction.UPLOAD else PurePosixPath(value)


def _destination_path(direction: Direction, value: str) -> Path | PurePosixPath:
    return PurePosixPath(value) if direction is Direction.UPLOAD else Path(value)


def _temporary_path(direction: Direction, value: str) -> Path | PurePosixPath:
    return PurePosixPath(value) if direction is Direction.UPLOAD else Path(value)
