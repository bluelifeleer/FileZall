from __future__ import annotations

from dataclasses import replace
from pathlib import Path, PurePosixPath

from filezall_core.models import Direction, TransferItem, TransferStatus
from filezall_core.protocols import RemoteFileClient
from filezall_core.resume import local_resume_offset, part_path_for
from filezall_core.transfer_repository import TransferRepository


class TransferRunner:
    def __init__(self, repository: TransferRepository) -> None:
        self._repository = repository

    def run_item(self, item: TransferItem, client: RemoteFileClient) -> TransferItem:
        try:
            self._repository.update_item_progress(
                item.id,
                bytes_transferred=item.bytes_transferred,
                status=TransferStatus.RUNNING,
            )
            if item.direction is Direction.UPLOAD:
                self._run_upload(item, client)
            else:
                self._run_download(item, client)
            completed = replace(
                item,
                bytes_transferred=item.size_bytes,
                status=TransferStatus.COMPLETED,
                last_error=None,
            )
            self._repository.update_item_progress(
                item.id,
                bytes_transferred=completed.bytes_transferred,
                status=completed.status,
            )
            return completed
        except Exception as exc:
            self._repository.update_item_progress(
                item.id,
                bytes_transferred=item.bytes_transferred,
                status=TransferStatus.FAILED,
                last_error=str(exc),
            )
            raise

    def _run_upload(self, item: TransferItem, client: RemoteFileClient) -> None:
        if not isinstance(item.source_path, Path):
            raise TypeError("Upload source path must be local")
        if not isinstance(item.destination_path, PurePosixPath):
            raise TypeError("Upload destination path must be remote")
        remote_part = _remote_path(item.temporary_path) or part_path_for(item.destination_path)
        offset = min(client.remote_size(remote_part) or 0, item.size_bytes)
        self._repository.update_item_progress(
            item.id,
            bytes_transferred=offset,
            status=TransferStatus.RUNNING,
        )
        client.upload_file_range(item.source_path, remote_part, offset)
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


def _remote_path(path: Path | PurePosixPath) -> PurePosixPath | None:
    return path if isinstance(path, PurePosixPath) else None
