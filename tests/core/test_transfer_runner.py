from pathlib import Path, PurePosixPath

import pytest

from filezall_core.models import ConflictPolicy, Direction, Protocol, TransferItem, TransferTask
from filezall_core.protocols import FakeRemoteClient
from filezall_core.storage import initialize_database
from filezall_core.transfer_repository import TransferRepository
from filezall_core.transfer_runner import TransferRunner


def test_transfer_runner_resumes_upload_from_remote_part_size(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    task = TransferTask(
        id="task-1",
        server_id="site-1",
        direction=Direction.UPLOAD,
        source_path=tmp_path,
        destination_path=PurePosixPath("/home/deploy"),
        protocol=Protocol.SFTP,
        conflict_policy=ConflictPolicy.OVERWRITE,
    )
    item = task.create_item("item-1", PurePosixPath("app.zip"), size_bytes=6)
    local_file = tmp_path / "app.zip"
    local_file.write_bytes(b"abcdef")
    repository.save_task(task, [item])
    client = FakeRemoteClient(entries={}, home=PurePosixPath("/home/deploy"))
    client.remote_sizes[PurePosixPath("/home/deploy/.filezall.app.zip.part")] = 3

    result = TransferRunner(repository).run_item(item, client)

    assert client.range_uploads == [
        (local_file, PurePosixPath("/home/deploy/.filezall.app.zip.part"), 3)
    ]
    assert client.renames == [
        (
            PurePosixPath("/home/deploy/.filezall.app.zip.part"),
            PurePosixPath("/home/deploy/app.zip"),
        )
    ]
    assert result.bytes_transferred == 6
    assert repository.get_item("item-1") == result


def test_transfer_runner_resumes_download_from_local_part_size(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    download_dir = tmp_path / "downloads"
    task = TransferTask(
        id="task-1",
        server_id="site-1",
        direction=Direction.DOWNLOAD,
        source_path=PurePosixPath("/home/deploy"),
        destination_path=download_dir,
        protocol=Protocol.SFTP,
        conflict_policy=ConflictPolicy.OVERWRITE,
    )
    item = task.create_item("item-1", PurePosixPath("app.zip"), size_bytes=6)
    local_part = download_dir / ".filezall.app.zip.part"
    local_part.parent.mkdir()
    local_part.write_bytes(b"abc")
    repository.save_task(task, [item])
    client = FakeRemoteClient(entries={}, home=PurePosixPath("/home/deploy"))

    result = TransferRunner(repository).run_item(item, client)

    assert client.range_downloads == [
        (PurePosixPath("/home/deploy/app.zip"), local_part, 3)
    ]
    assert (download_dir / "app.zip").read_bytes() == b"abc"
    assert not local_part.exists()
    assert result.bytes_transferred == 6
    assert repository.get_item("item-1") == result


def test_transfer_runner_records_failed_status_when_client_raises(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    task = TransferTask(
        id="task-1",
        server_id="site-1",
        direction=Direction.UPLOAD,
        source_path=tmp_path,
        destination_path=PurePosixPath("/home/deploy"),
        protocol=Protocol.SFTP,
        conflict_policy=ConflictPolicy.OVERWRITE,
    )
    item = task.create_item("item-1", PurePosixPath("app.zip"), size_bytes=6)
    (tmp_path / "app.zip").write_bytes(b"abcdef")
    repository.save_task(task, [item])

    with pytest.raises(RuntimeError, match="network down"):
        TransferRunner(repository).run_item(item, FailingRemoteClient())

    failed = repository.get_item("item-1")
    assert failed is not None
    assert failed.status.value == "failed"
    assert failed.last_error == "network down"


class FailingRemoteClient(FakeRemoteClient):
    def __init__(self) -> None:
        super().__init__(entries={}, home=PurePosixPath("/home/deploy"))

    def upload_file_range(
        self,
        local_path: Path,
        remote_path: PurePosixPath,
        offset: int,
    ) -> None:
        raise RuntimeError("network down")


def _repository(tmp_path: Path) -> TransferRepository:
    database = tmp_path / "filezall.sqlite3"
    initialize_database(database)
    return TransferRepository(database)
