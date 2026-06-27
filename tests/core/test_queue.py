from pathlib import Path, PurePosixPath

from filezall_core.models import ConflictPolicy, Direction, Protocol, TransferStatus, TransferTask
from filezall_core.protocols import FakeRemoteClient
from filezall_core.queue import TransferQueue
from filezall_core.storage import initialize_database
from filezall_core.transfer_settings import TransferSettings
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


def test_queue_records_transfer_metrics(tmp_path: Path) -> None:
    queue, _client = _queue(tmp_path)
    task = _upload_task(tmp_path)
    local_file = tmp_path / "app.zip"
    local_file.write_bytes(b"abcdef")
    item = task.create_item("item-1", PurePosixPath("app.zip"), size_bytes=6)
    queue.add_task(task, [item])

    queue.run_next("site-1")

    updated = queue.list_items()[0]
    assert updated.started_at is not None
    assert updated.updated_at is not None
    assert updated.bytes_per_second >= 0
    assert updated.remaining_seconds == 0
    assert updated.retry_count == 0
    assert updated.failure_reason is None


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


def test_queue_respects_concurrency_limit(tmp_path: Path) -> None:
    queue, client = _queue(
        tmp_path,
        settings=TransferSettings(max_concurrent=0, bytes_per_second_limit=2048),
    )
    task = _upload_task(tmp_path)
    local_file = tmp_path / "app.zip"
    local_file.write_bytes(b"abcdef")
    item = task.create_item("item-1", PurePosixPath("app.zip"), size_bytes=6)
    queue.add_task(task, [item])

    result = queue.run_next("site-1")

    assert result is None
    assert client.range_uploads == []
    assert queue.settings.bytes_per_second_limit == 2048


def test_queue_limits_concurrency_per_server_without_blocking_other_servers(
    tmp_path: Path,
) -> None:
    queue, client = _queue(
        tmp_path,
        settings=TransferSettings(max_concurrent=2, max_concurrent_per_server=1),
    )
    site_1_task = _upload_task(tmp_path)
    site_2_task = TransferTask(
        id="task-2",
        server_id="site-2",
        direction=Direction.UPLOAD,
        source_path=tmp_path,
        destination_path=PurePosixPath("/home/deploy"),
        protocol=Protocol.SFTP,
        conflict_policy=ConflictPolicy.OVERWRITE,
    )
    (tmp_path / "app.zip").write_bytes(b"abcdef")
    (tmp_path / "other.zip").write_bytes(b"ghijkl")
    site_1_item = site_1_task.create_item("item-1", PurePosixPath("app.zip"), size_bytes=6)
    site_2_item = site_2_task.create_item("item-2", PurePosixPath("other.zip"), size_bytes=6)
    queue.add_task(site_1_task, [site_1_item])
    queue.add_task(site_2_task, [site_2_item])

    assert queue.reserve_slot("site-1") is True

    blocked = queue.run_next("site-1")
    allowed = queue.run_next("site-2")

    assert blocked is None
    assert allowed is not None
    assert allowed.status is TransferStatus.COMPLETED
    assert client.range_uploads == [
        (tmp_path / "other.zip", PurePosixPath("/home/deploy/.filezall.other.zip.part"), 0)
    ]

    queue.release_slot("site-1")


def test_queue_records_retry_state_and_failure_reason(tmp_path: Path) -> None:
    database = tmp_path / "filezall.sqlite3"
    initialize_database(database)
    repository = TransferRepository(database)

    class FailingClient(FakeRemoteClient):
        def upload_file_range(self, *args, **kwargs) -> None:
            raise RuntimeError("network down")

    queue = TransferQueue(
        repository=repository,
        runner=TransferRunner(repository),
        client_factory=lambda _server_id: FailingClient(entries={}, home=PurePosixPath("/home/deploy")),
    )
    task = _upload_task(tmp_path)
    local_file = tmp_path / "app.zip"
    local_file.write_bytes(b"abcdef")
    item = task.create_item("item-1", PurePosixPath("app.zip"), size_bytes=6)
    queue.add_task(task, [item])

    result = queue.run_next("site-1")

    assert result is not None
    assert result.status is TransferStatus.FAILED
    assert result.retry_count == 3
    assert result.failure_reason == "network down"
    assert result.last_error == "network down"


def _queue(
    tmp_path: Path,
    settings=None,
) -> tuple[TransferQueue, FakeRemoteClient]:
    database = tmp_path / "filezall.sqlite3"
    initialize_database(database)
    repository = TransferRepository(database)
    client = FakeRemoteClient(entries={}, home=PurePosixPath("/home/deploy"))
    queue = TransferQueue(
        repository=repository,
        runner=TransferRunner(repository),
        client_factory=lambda _server_id: client,
        settings=settings,
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
