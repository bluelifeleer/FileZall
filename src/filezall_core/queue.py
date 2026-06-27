from __future__ import annotations

from collections import defaultdict
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
            if item.status in {TransferStatus.PENDING, TransferStatus.RUNNING}:
                self.repository.update_item_state(item.id, TransferStatus.PAUSED)

    def resume_task(self, task_id: str) -> None:
        for item in self.repository.list_items(task_id):
            if item.status is TransferStatus.PAUSED:
                self.repository.update_item_state(item.id, TransferStatus.PENDING)

    def cancel_task(self, task_id: str) -> None:
        for item in self.repository.list_items(task_id):
            if item.status is not TransferStatus.COMPLETED:
                self.repository.update_item_state(item.id, TransferStatus.CANCELED)

    def retry_failed(self, task_id: str) -> None:
        for item in self.repository.list_items(task_id):
            if item.status is TransferStatus.FAILED:
                self.repository.update_item_state(
                    item.id,
                    TransferStatus.PENDING,
                    last_error=None,
                    failure_reason=None,
                    next_retry_at=None,
                    retry_count=item.retry_count + 1,
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

    def _ready_items(self) -> list[TransferItem]:
        now = self._clock()
        pending = self.repository.list_all_items(status=TransferStatus.PENDING)
        retrying = [
            item
            for item in self.repository.list_all_items(status=TransferStatus.RETRYING)
            if item.next_retry_at is None or item.next_retry_at <= now
        ]
        return [*pending, *retrying]
