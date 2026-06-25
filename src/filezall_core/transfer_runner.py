from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path, PurePosixPath

from filezall_core.models import Direction, TransferItem, TransferStatus
from filezall_core.protocols import RemoteFileClient
from filezall_core.resume import local_resume_offset, part_path_for
from filezall_core.transfer_repository import TransferRepository


class TransferRunner:
    def __init__(self, repository: TransferRepository) -> None:
        self._repository = repository

    def run_item(
        self,
        item: TransferItem,
        client: RemoteFileClient,
        progress_callback: Callable[[TransferItem], None] | None = None,
    ) -> TransferItem:
        try:
            self._update_progress(
                item,
                item.bytes_transferred,
                TransferStatus.RUNNING,
                progress_callback=progress_callback,
            )
            if item.direction is Direction.UPLOAD:
                self._run_upload(item, client, progress_callback)
            else:
                self._run_download(item, client)
            completed = replace(
                item,
                bytes_transferred=item.size_bytes,
                status=TransferStatus.COMPLETED,
                last_error=None,
            )
            self._update_progress(
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
        client.upload_file_range(
            item.source_path,
            remote_part,
            offset,
            progress_callback=lambda bytes_transferred: self._update_progress(
                item,
                bytes_transferred,
                TransferStatus.RUNNING,
                progress_callback=progress_callback,
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
        updated = replace(
            item,
            bytes_transferred=min(bytes_transferred, item.size_bytes),
            status=status,
            last_error=last_error,
        )
        self._repository.update_item_progress(
            updated.id,
            bytes_transferred=updated.bytes_transferred,
            status=updated.status,
            last_error=updated.last_error,
        )
        if progress_callback is not None:
            progress_callback(updated)
        return updated


def _remote_path(path: Path | PurePosixPath) -> PurePosixPath | None:
    return path if isinstance(path, PurePosixPath) else None
