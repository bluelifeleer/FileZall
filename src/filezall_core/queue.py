from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from filezall_core.models import TransferItem, TransferStatus, TransferTask
from filezall_core.protocols import RemoteFileClient
from filezall_core.transfer_settings import TransferSettings
from filezall_core.transfer_repository import TransferRepository
from filezall_core.transfer_runner import TransferRunner


class TransferQueue:
    def __init__(
        self,
        repository: TransferRepository,
        runner: TransferRunner,
        client_factory: Callable[[str], RemoteFileClient],
        settings: TransferSettings | None = None,
        max_attempts: int = 3,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self._runner = runner
        self._client_factory = client_factory
        self.settings = settings or TransferSettings()
        self._running_count = 0
        self._running_count_by_server: dict[str, int] = defaultdict(int)
        self._max_attempts = max_attempts
        self._clock = clock or (lambda: datetime.now(UTC))

    def add_task(self, task: TransferTask, items: list[TransferItem]) -> None:
        self.repository.save_task(task, items)

    def list_items(
        self,
        status: TransferStatus | None = None,
        server_id: str | None = None,
    ) -> list[TransferItem]:
        items = self.repository.list_all_items(status=status)
        if server_id is not None:
            return [item for item in items if item.server_id == server_id]
        return items

    def pause_task(self, task_id: str) -> None:
        for item in self.repository.list_items(task_id):
            if item.status in {
                TransferStatus.PENDING,
                TransferStatus.RUNNING,
                TransferStatus.RETRYING,
            }:
                self.repository.update_item_state(
                    item.id,
                    TransferStatus.PAUSED,
                    next_retry_at=None,
                )

    def resume_task(self, task_id: str) -> None:
        for item in self.repository.list_items(task_id):
            if item.status is TransferStatus.PAUSED:
                self.repository.update_item_state(
                    item.id,
                    TransferStatus.PENDING,
                    next_retry_at=None,
                )

    def cancel_task(self, task_id: str) -> None:
        for item in self.repository.list_items(task_id):
            if item.status is not TransferStatus.COMPLETED:
                self.repository.update_item_state(
                    item.id,
                    TransferStatus.CANCELED,
                    next_retry_at=None,
                )

    def retry_failed(self, task_id: str) -> None:
        for item in self.repository.list_items(task_id):
            if item.status in {TransferStatus.FAILED, TransferStatus.RETRYING}:
                retry_count = (
                    item.retry_count + 1
                    if item.status is TransferStatus.FAILED
                    else item.retry_count
                )
                self.repository.update_item_state(
                    item.id,
                    TransferStatus.PENDING,
                    last_error=None,
                    failure_reason=None,
                    next_retry_at=None,
                    retry_count=retry_count,
                )

    def can_start_transfer(self, server_id: str) -> bool:
        if self._running_count >= self.settings.max_concurrent:
            return False
        max_per_server = (
            self.settings.max_concurrent
            if self.settings.max_concurrent_per_server is None
            else self.settings.max_concurrent_per_server
        )
        return self._running_count_by_server[server_id] < max_per_server

    def reserve_slot(self, server_id: str) -> bool:
        if not self.can_start_transfer(server_id):
            return False
        self._running_count += 1
        self._running_count_by_server[server_id] += 1
        return True

    def release_slot(self, server_id: str) -> None:
        if self._running_count > 0:
            self._running_count -= 1
        if self._running_count_by_server[server_id] > 0:
            self._running_count_by_server[server_id] -= 1

    def run_next(
        self,
        server_id: str,
        client: RemoteFileClient | None = None,
        progress_callback: Callable[[TransferItem], None] | None = None,
    ) -> TransferItem | None:
        for item in self._ready_items():
            if item.server_id == server_id:
                if not self.reserve_slot(server_id):
                    return None
                transfer_client = client or self._client_factory(server_id)
                try:
                    return self._run_item_with_retries(
                        item,
                        transfer_client,
                        progress_callback=progress_callback,
                    )
                finally:
                    self.release_slot(server_id)
        return None

    def _run_item_with_retries(
        self,
        item: TransferItem,
        transfer_client: RemoteFileClient,
        progress_callback: Callable[[TransferItem], None] | None = None,
    ) -> TransferItem:
        try:
            return self._runner.run_item(
                item,
                transfer_client,
                progress_callback=progress_callback,
            )
        except Exception as exc:
            reason = str(exc)
            retry_count = item.retry_count + 1
            status = (
                TransferStatus.FAILED
                if retry_count >= self._max_attempts
                else TransferStatus.RETRYING
            )
            next_retry_at = (
                None
                if status is TransferStatus.FAILED
                else self._clock() + timedelta(seconds=2**retry_count)
            )
            self.repository.update_item_state(
                item.id,
                status,
                last_error=reason,
                retry_count=retry_count,
                failure_reason=reason,
                next_retry_at=next_retry_at,
            )
            current = self.repository.get_item(item.id) or item
            if progress_callback is not None:
                progress_callback(current)
            return current

    def recover_pending(self) -> list[TransferItem]:
        return self.repository.list_recoverable_items()

    def diagnostic_snapshot(self, now: datetime | None = None) -> dict:
        now = now or self._clock()
        items = self.repository.list_all_items()
        retrying = [item for item in items if item.status is TransferStatus.RETRYING]
        waiting_retrying = [
            item for item in retrying if item.next_retry_at is not None and item.next_retry_at > now
        ]
        ready_retrying = [
            item for item in retrying if item.next_retry_at is None or item.next_retry_at <= now
        ]
        failures = [
            item
            for item in items
            if item.status in {TransferStatus.FAILED, TransferStatus.RETRYING}
            and (item.failure_reason or item.last_error)
        ]
        next_retry_at = min(
            (item.next_retry_at for item in waiting_retrying if item.next_retry_at is not None),
            default=None,
        )
        return {
            "total": len(items),
            "by_status": dict(sorted(Counter(item.status.value for item in items).items())),
            "slots": {
                "running": self._running_count,
                "max_concurrent": self.settings.max_concurrent,
                "max_concurrent_per_server": self.settings.max_concurrent_per_server,
                "by_server": dict(sorted(self._running_count_by_server.items())),
            },
            "retrying": {
                "total": len(retrying),
                "ready": len(ready_retrying),
                "waiting": len(waiting_retrying),
                "next_retry_at": next_retry_at.isoformat() if next_retry_at else None,
            },
            "failures": {
                "total": len([item for item in items if item.status is TransferStatus.FAILED]),
                "recent": [_diagnostic_failure(item) for item in failures[-10:]],
            },
        }

    def _ready_items(self) -> list[TransferItem]:
        now = self._clock()
        pending = self.repository.list_all_items(status=TransferStatus.PENDING)
        retrying = [
            item
            for item in self.repository.list_all_items(status=TransferStatus.RETRYING)
            if item.next_retry_at is None or item.next_retry_at <= now
        ]
        return [*pending, *retrying]


def _diagnostic_failure(item: TransferItem) -> dict:
    return {
        "item_id": item.id,
        "task_id": item.task_id,
        "server_id": item.server_id,
        "status": item.status.value,
        "retry_count": item.retry_count,
        "reason": item.failure_reason or item.last_error or "",
    }
