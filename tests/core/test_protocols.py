from pathlib import Path, PurePosixPath

from filezall_core.models import RemoteFileEntry
from filezall_core.protocols import FakeRemoteClient


def test_fake_remote_client_lists_home_directory() -> None:
    client = FakeRemoteClient(
        entries={
            PurePosixPath("/home/deploy"): [
                RemoteFileEntry(
                    path=PurePosixPath("/home/deploy/app.log"),
                    name="app.log",
                    is_dir=False,
                    size_bytes=100,
                    modified_time=None,
                )
            ]
        },
        home=PurePosixPath("/home/deploy"),
    )

    assert client.home_directory() == PurePosixPath("/home/deploy")
    assert client.list_directory(PurePosixPath("/home/deploy"))[0].name == "app.log"


def test_fake_remote_client_records_upload_and_download(tmp_path: Path) -> None:
    client = FakeRemoteClient(entries={}, home=PurePosixPath("/home/deploy"))
    local_file = tmp_path / "app.zip"
    local_file.write_text("build", encoding="utf-8")
    download_file = tmp_path / "download.zip"

    client.upload_file(local_file, PurePosixPath("/home/deploy/app.zip"))
    client.download_file(PurePosixPath("/home/deploy/app.zip"), download_file)

    assert client.uploads == [(local_file, PurePosixPath("/home/deploy/app.zip"))]
    assert client.downloads == [(PurePosixPath("/home/deploy/app.zip"), download_file)]


def test_fake_remote_client_reports_remote_size_and_resume_calls(tmp_path: Path) -> None:
    client = FakeRemoteClient(entries={}, home=PurePosixPath("/home/deploy"))
    local_file = tmp_path / "app.zip"
    local_file.write_bytes(b"abcdef")
    remote_part = PurePosixPath("/home/deploy/.filezall.app.zip.part")
    client.remote_sizes[remote_part] = 3

    assert client.remote_size(remote_part) == 3

    client.upload_file_range(local_file, remote_part, offset=3)
    client.download_file_range(PurePosixPath("/home/deploy/app.zip"), tmp_path / ".part", offset=2)
    client.rename(remote_part, PurePosixPath("/home/deploy/app.zip"))

    assert client.range_uploads == [(local_file, remote_part, 3)]
    assert client.range_downloads == [
        (PurePosixPath("/home/deploy/app.zip"), tmp_path / ".part", 2)
    ]
    assert client.renames == [(remote_part, PurePosixPath("/home/deploy/app.zip"))]
