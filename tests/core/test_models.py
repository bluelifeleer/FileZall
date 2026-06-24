from pathlib import Path, PurePosixPath

from filezall_core.models import (
    AuthMode,
    ConflictPolicy,
    Direction,
    Protocol,
    SiteProfile,
    TransferItem,
    TransferStatus,
    TransferTask,
)


def test_site_profile_defaults_to_user_home_remote_path() -> None:
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )

    assert site.default_remote_path == PurePosixPath("~")
    assert site.agent_enabled is False


def test_directory_task_expands_relative_file_items() -> None:
    task = TransferTask(
        id="task-1",
        server_id="site-1",
        direction=Direction.UPLOAD,
        source_path=Path("D:/release"),
        destination_path=PurePosixPath("/var/www/release"),
        protocol=Protocol.SFTP,
        conflict_policy=ConflictPolicy.SKIP,
    )

    item = task.create_item(
        item_id="item-1",
        relative_path=PurePosixPath("assets/app.js"),
        size_bytes=1200,
    )

    assert item.source_path == Path("D:/release/assets/app.js")
    assert item.destination_path == PurePosixPath("/var/www/release/assets/app.js")
    assert item.status == TransferStatus.PENDING
    assert item.bytes_transferred == 0


def test_transfer_item_marks_completion_when_all_bytes_transferred() -> None:
    item = TransferItem(
        id="item-1",
        task_id="task-1",
        server_id="site-1",
        direction=Direction.DOWNLOAD,
        source_path=PurePosixPath("/data/archive.zip"),
        destination_path=Path("D:/Downloads/archive.zip"),
        temporary_path=Path("D:/Downloads/.filezall.archive.zip.part"),
        size_bytes=4096,
        protocol=Protocol.SFTP,
    )

    completed = item.with_progress(4096)

    assert completed.status == TransferStatus.COMPLETED
    assert completed.bytes_transferred == 4096
