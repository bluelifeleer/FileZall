from pathlib import Path, PurePosixPath

from filezall_core.models import Direction, Protocol, TransferItem
from filezall_core.resume import local_resume_offset, part_path_for


def test_part_path_for_local_and_remote_paths() -> None:
    assert part_path_for(Path("D:/Downloads/app.zip")) == Path(
        "D:/Downloads/.filezall.app.zip.part"
    )
    assert part_path_for(PurePosixPath("/home/deploy/app.zip")) == PurePosixPath(
        "/home/deploy/.filezall.app.zip.part"
    )


def test_local_resume_offset_uses_existing_part_size(tmp_path: Path) -> None:
    part = tmp_path / ".filezall.app.zip.part"
    part.write_bytes(b"abc")
    item = TransferItem(
        id="item-1",
        task_id="task-1",
        server_id="site-1",
        direction=Direction.DOWNLOAD,
        source_path=PurePosixPath("/home/deploy/app.zip"),
        destination_path=tmp_path / "app.zip",
        temporary_path=part,
        size_bytes=10,
        protocol=Protocol.SFTP,
    )

    assert local_resume_offset(item) == 3
