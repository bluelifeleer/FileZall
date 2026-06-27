from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from time import monotonic, sleep

from filezall_core.models import Direction, TransferItem, TransferStatus
from filezall_core.protocols import RemoteFileClient
from filezall_core.resume import local_resume_offset, part_path_for
from filezall_core.transfer_repository import TransferRepository


class TransferRunner:
    def __init__(
        self,
        repository: TransferRepository,
        throttle_clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._repository = repository
        self._throttle_clock = throttle_clock
        self._sleeper = sleeper

    def run_item(
        self,
        item: TransferItem,
        client: RemoteFileClient,
        progress_callback: Callable[[TransferItem], None] | None = None,
        bytes_per_second_limit: int | None = None,
    ) -> TransferItem:
        try:
            self._update_progress(
                item,
                item.bytes_transferred,
                TransferStatus.RUNNING,
                progress_callback=progress_callback,
            )
            if item.direction is Direction.UPLOAD:
                self._run_upload(
                    item,
                    client,
                    progress_callback,
                    bytes_per_second_limit=bytes_per_second_limit,
                )
            else:
                self._run_download(item, client)
            current = self._repository.get_item(item.id) or item
            completed = replace(
                current,
                bytes_transferred=item.size_bytes,
                status=TransferStatus.COMPLETED,
                last_error=None,
                failure_reason=None,
            )
            completed = self._update_progress(
                completed,
                completed.bytes_transferred,
                completed.status,
                progress_callback=progress_callback,
            )
            return completed
        except Exception as exc:
            self._update_progress(
                item,
                item.bytes_transferred,
                TransferStatus.FAILED,
                last_error=str(exc),
                progress_callback=progress_callback,
            )
            raise

    def _run_upload(
        self,
        item: TransferItem,
        client: RemoteFileClient,
        progress_callback: Callable[[TransferItem], None] | None = None,
        bytes_per_second_limit: int | None = None,
    ) -> None:
        if not isinstance(item.source_path, Path):
            raise TypeError("Upload source path must be local")
        if not isinstance(item.destination_path, PurePosixPath):
            raise TypeError("Upload destination path must be remote")
        remote_part = _remote_path(item.temporary_path) or part_path_for(item.destination_path)
        offset = min(client.remote_size(remote_part) or 0, item.size_bytes)
        self._update_progress(
            item,
            offset,
            TransferStatus.RUNNING,
            progress_callback=progress_callback,
        )
        throttle = _TransferThrottle(
            offset,
            bytes_per_second_limit,
            clock=self._throttle_clock,
            sleeper=self._sleeper,
        )
        client.upload_file_range(
            item.source_path,
            remote_part,
            offset,
            progress_callback=lambda bytes_transferred: (
                throttle.wait(bytes_transferred),
                self._update_progress(
                    item,
                    bytes_transferred,
                    TransferStatus.RUNNING,
                    progress_callback=progress_callback,
                ),
            ),
        )
        client.rename(remote_part, item.destination_path)

    def _run_download(self, item: TransferItem, client: RemoteFileClient) -> None:
        if not isinstance(item.source_path, PurePosixPath):
            raise TypeError("Download source path must be remote")
        if not isinstance(item.destination_path, Path):
            raise TypeError("Download destination path must be local")
        if not isinstance(item.temporary_path, Path):
            raise TypeError("Download temporary path must be local")
        offset = local_resume_offset(item)
        self._repository.update_item_progress(
            item.id,
            bytes_transferred=offset,
            status=TransferStatus.RUNNING,
        )
        client.download_file_range(item.source_path, item.temporary_path, offset)
        item.temporary_path.replace(item.destination_path)

    def _update_progress(
        self,
        item: TransferItem,
        bytes_transferred: int,
        status: TransferStatus,
        last_error: str | None = None,
        progress_callback: Callable[[TransferItem], None] | None = None,
    ) -> TransferItem:
        persisted = self._repository.get_item(item.id) or item
        now = datetime.now(UTC)
        started_at = persisted.started_at or now
        safe_bytes = min(bytes_transferred, item.size_bytes)
        elapsed_seconds = max((now - started_at).total_seconds(), 0.0)
        bytes_per_second = safe_bytes / elapsed_seconds if elapsed_seconds > 0 else 0.0
        remaining_bytes = max(item.size_bytes - safe_bytes, 0)
        remaining_seconds = (
            0
            if status is TransferStatus.COMPLETED
            else remaining_bytes / bytes_per_second
            if bytes_per_second > 0
            else None
        )
        updated = replace(
            item,
            bytes_transferred=safe_bytes,
            status=status,
            last_error=last_error,
            started_at=started_at,
            updated_at=now,
            bytes_per_second=bytes_per_second,
            remaining_seconds=remaining_seconds,
            failure_reason=last_error,
        )
        self._repository.update_item_progress(
            updated.id,
            bytes_transferred=updated.bytes_transferred,
            status=updated.status,
            last_error=updated.last_error,
            started_at=updated.started_at,
            updated_at=updated.updated_at,
            bytes_per_second=updated.bytes_per_second,
            remaining_seconds=updated.remaining_seconds,
            failure_reason=updated.failure_reason,
        )
        if progress_callback is not None:
            progress_callback(updated)
        return updated


def _remote_path(path: Path | PurePosixPath) -> PurePosixPath | None:
    return path if isinstance(path, PurePosixPath) else None


class _TransferThrottle:
    def __init__(
        self,
        offset: int,
        bytes_per_second_limit: int | None,
        *,
        clock: Callable[[], float],
        sleeper: Callable[[float], None],
    ) -> None:
        self._offset = offset
        self._limit = bytes_per_second_limit
        self._clock = clock
        self._sleeper = sleeper
        self._started_at = clock()
        self._slept_seconds = 0.0

    def wait(self, bytes_transferred: int) -> None:
        if self._limit is None or self._limit <= 0:
            return
        transferred = max(bytes_transferred - self._offset, 0)
        expected_elapsed = transferred / self._limit
        elapsed = (self._clock() - self._started_at) + self._slept_seconds
        delay = expected_elapsed - elapsed
        if delay > 0:
            self._sleeper(delay)
            self._slept_seconds += delay
