from __future__ import annotations

from collections.abc import Callable

from filezall_core.models import TransferItem, TransferStatus, TransferTask
from filezall_core.protocols import RemoteFileClient
from filezall_core.transfer_repository import TransferRepository
from filezall_core.transfer_runner import TransferRunner


class TransferQueue:
    def __init__(
        self,
        repository: TransferRepository,
        runner: TransferRunner,
        client_factory: Callable[[str], RemoteFileClient],
    ) -> None:
        self.repository = repository
        self._runner = runner
        self._client_factory = client_factory

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
                    retry_count=item.retry_count + 1,
                )

    def run_next(
        self,
        server_id: str,
        client: RemoteFileClient | None = None,
        progress_callback: Callable[[TransferItem], None] | None = None,
    ) -> TransferItem | None:
        for item in self.repository.list_all_items(status=TransferStatus.PENDING):
            if item.server_id == server_id:
                transfer_client = client or self._client_factory(server_id)
                return self._runner.run_item(
                    item,
                    transfer_client,
                    progress_callback=progress_callback,
                )
        return None

    def recover_pending(self) -> list[TransferItem]:
        return self.repository.list_recoverable_items()
