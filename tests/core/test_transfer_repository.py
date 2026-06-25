from pathlib import Path, PurePosixPath

from filezall_core.models import (
    ConflictPolicy,
    Direction,
    Protocol,
    TransferStatus,
    TransferTask,
)
from filezall_core.storage import initialize_database
from filezall_core.transfer_repository import TransferRepository


def test_transfer_repository_saves_task_and_items(tmp_path: Path) -> None:
    database = tmp_path / "filezall.sqlite3"
    initialize_database(database)
    repository = TransferRepository(database)
    task = TransferTask(
        id="task-1",
        server_id="site-1",
        direction=Direction.UPLOAD,
        source_path=tmp_path,
        destination_path=PurePosixPath("/home/deploy"),
        protocol=Protocol.SFTP,
        conflict_policy=ConflictPolicy.OVERWRITE,
    )
    item = task.create_item(
        item_id="item-1",
        relative_path=PurePosixPath("app.zip"),
        size_bytes=4096,
    )

    repository.save_task(task, [item])

    assert repository.get_task("task-1") == task
    assert repository.list_items("task-1") == [item]


def test_transfer_repository_updates_item_progress_and_status(tmp_path: Path) -> None:
    database = tmp_path / "filezall.sqlite3"
    initialize_database(database)
    repository = TransferRepository(database)
    task = TransferTask(
        id="task-1",
        server_id="site-1",
        direction=Direction.DOWNLOAD,
        source_path=PurePosixPath("/home/deploy"),
        destination_path=tmp_path,
        protocol=Protocol.SFTP,
        conflict_policy=ConflictPolicy.OVERWRITE,
    )
    item = task.create_item("item-1", PurePosixPath("app.zip"), size_bytes=4096)
    repository.save_task(task, [item])

    repository.update_item_progress(
        "item-1",
        bytes_transferred=2048,
        status=TransferStatus.RUNNING,
    )

    updated = repository.get_item("item-1")
    assert updated is not None
    assert updated.bytes_transferred == 2048
    assert updated.status == TransferStatus.RUNNING


def test_transfer_repository_lists_recoverable_items_after_restart(tmp_path: Path) -> None:
    database = tmp_path / "filezall.sqlite3"
    initialize_database(database)
    repository = TransferRepository(database)
    task = TransferTask(
        id="task-1",
        server_id="site-1",
        direction=Direction.UPLOAD,
        source_path=tmp_path,
        destination_path=PurePosixPath("/home/deploy"),
        protocol=Protocol.SFTP,
        conflict_policy=ConflictPolicy.OVERWRITE,
    )
    pending = task.create_item("pending", PurePosixPath("pending.zip"), size_bytes=10)
    completed = task.create_item("done", PurePosixPath("done.zip"), size_bytes=10).with_progress(10)
    repository.save_task(task, [pending, completed])

    recoverable = repository.list_recoverable_items()

    assert [item.id for item in recoverable] == ["pending"]
