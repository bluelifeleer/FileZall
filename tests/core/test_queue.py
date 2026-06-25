from pathlib import Path, PurePosixPath

from filezall_core.models import ConflictPolicy, Direction, Protocol, TransferStatus, TransferTask
from filezall_core.protocols import FakeRemoteClient
from filezall_core.queue import TransferQueue
from filezall_core.storage import initialize_database
from filezall_core.transfer_repository import TransferRepository
from filezall_core.transfer_runner import TransferRunner


def test_transfer_queue_adds_task_and_lists_items(tmp_path: Path) -> None:
    queue, _client = _queue(tmp_path)
    task = _upload_task(tmp_path)
    item = task.create_item("item-1", PurePosixPath("app.zip"), size_bytes=6)

    queue.add_task(task, [item])

    assert queue.list_items() == [item]
    assert queue.list_items(status=TransferStatus.PENDING) == [item]


def test_transfer_queue_pauses_resumes_and_cancels_task_items(tmp_path: Path) -> None:
    queue, _client = _queue(tmp_path)
    task = _upload_task(tmp_path)
    item = task.create_item("item-1", PurePosixPath("app.zip"), size_bytes=6)
    queue.add_task(task, [item])

    queue.pause_task("task-1")
    assert queue.list_items()[0].status == TransferStatus.PAUSED

    queue.resume_task("task-1")
    assert queue.list_items()[0].status == TransferStatus.PENDING

    queue.cancel_task("task-1")
    assert queue.list_items()[0].status == TransferStatus.CANCELED


def test_transfer_queue_retries_failed_items(tmp_path: Path) -> None:
    queue, _client = _queue(tmp_path)
    task = _upload_task(tmp_path)
    item = task.create_item("item-1", PurePosixPath("app.zip"), size_bytes=6)
    queue.add_task(task, [item])
    queue.repository.update_item_progress(
        "item-1",
        bytes_transferred=2,
        status=TransferStatus.FAILED,
        last_error="network down",
    )

    queue.retry_failed("task-1")

    retried = queue.list_items()[0]
    assert retried.status == TransferStatus.PENDING
    assert retried.retry_count == 1
    assert retried.last_error is None


def test_transfer_queue_runs_next_pending_item_for_server(tmp_path: Path) -> None:
    queue, client = _queue(tmp_path)
    task = _upload_task(tmp_path)
    local_file = tmp_path / "app.zip"
    local_file.write_bytes(b"abcdef")
    item = task.create_item("item-1", PurePosixPath("app.zip"), size_bytes=6)
    queue.add_task(task, [item])

    result = queue.run_next("site-1")

    assert result is not None
    assert result.status == TransferStatus.COMPLETED
    assert client.range_uploads == [
        (local_file, PurePosixPath("/home/deploy/.filezall.app.zip.part"), 0)
    ]
    assert queue.list_items()[0].status == TransferStatus.COMPLETED


def test_transfer_queue_recovers_unfinished_items_after_restart(tmp_path: Path) -> None:
    queue, _client = _queue(tmp_path)
    task = _upload_task(tmp_path)
    item = task.create_item("item-1", PurePosixPath("app.zip"), size_bytes=6)
    queue.add_task(task, [item])

    restarted, _client = _queue(tmp_path)

    assert restarted.recover_pending() == [item]


def test_transfer_queue_lists_items_for_one_server(tmp_path: Path) -> None:
    queue, _client = _queue(tmp_path)
    task_1 = _upload_task(tmp_path)
    task_2 = TransferTask(
        id="task-2",
        server_id="site-2",
        direction=Direction.UPLOAD,
        source_path=tmp_path,
        destination_path=PurePosixPath("/home/deploy"),
        protocol=Protocol.SFTP,
        conflict_policy=ConflictPolicy.OVERWRITE,
    )
    item_1 = task_1.create_item("item-1", PurePosixPath("app.zip"), size_bytes=6)
    item_2 = task_2.create_item("item-2", PurePosixPath("other.zip"), size_bytes=6)
    queue.add_task(task_1, [item_1])
    queue.add_task(task_2, [item_2])

    assert queue.list_items(server_id="site-1") == [item_1]


def _queue(tmp_path: Path) -> tuple[TransferQueue, FakeRemoteClient]:
    database = tmp_path / "filezall.sqlite3"
    initialize_database(database)
    repository = TransferRepository(database)
    client = FakeRemoteClient(entries={}, home=PurePosixPath("/home/deploy"))
    queue = TransferQueue(
        repository=repository,
        runner=TransferRunner(repository),
        client_factory=lambda _server_id: client,
    )
    return queue, client


def _upload_task(tmp_path: Path) -> TransferTask:
    return TransferTask(
        id="task-1",
        server_id="site-1",
        direction=Direction.UPLOAD,
        source_path=tmp_path,
        destination_path=PurePosixPath("/home/deploy"),
        protocol=Protocol.SFTP,
        conflict_policy=ConflictPolicy.OVERWRITE,
    )
