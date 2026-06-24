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
