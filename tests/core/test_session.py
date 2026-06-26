from pathlib import Path, PurePosixPath

from filezall_core.models import AuthMode, Protocol, RemoteFileEntry, SiteProfile
from filezall_core.protocols import FakeRemoteClient
from filezall_core.session import RemoteSession


def test_remote_session_connects_and_lists_server_home_for_tilde_default() -> None:
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )
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

    session = RemoteSession(site=site, client=client)
    entries = session.connect_and_list_default(password="secret")

    assert client.connected_site == site
    assert client.password == "secret"
    assert session.current_remote_path == PurePosixPath("/home/deploy")
    assert entries[0].name == "app.log"


def test_remote_session_lists_saved_default_remote_path_when_not_tilde() -> None:
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
        default_remote_path=PurePosixPath("/var/www"),
    )
    client = FakeRemoteClient(
        entries={
            PurePosixPath("/var/www"): [
                RemoteFileEntry(
                    path=PurePosixPath("/var/www/index.html"),
                    name="index.html",
                    is_dir=False,
                    size_bytes=200,
                    modified_time=None,
                )
            ]
        },
        home=PurePosixPath("/home/deploy"),
    )

    session = RemoteSession(site=site, client=client)
    entries = session.connect_and_list_default(password="secret")

    assert session.current_remote_path == PurePosixPath("/var/www")
    assert entries[0].name == "index.html"


def test_remote_session_uploads_and_downloads_one_file(tmp_path: Path) -> None:
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )
    client = FakeRemoteClient(entries={}, home=PurePosixPath("/home/deploy"))
    session = RemoteSession(site=site, client=client)
    session.connect_and_list_default(password="secret")
    local_file = tmp_path / "build.zip"
    local_file.write_text("zip", encoding="utf-8")
    download_file = tmp_path / "copy.zip"

    session.upload_file(local_file, PurePosixPath("/home/deploy/build.zip"))
    session.download_file(PurePosixPath("/home/deploy/build.zip"), download_file)

    assert client.uploads == [(local_file, PurePosixPath("/home/deploy/build.zip"))]
    assert client.downloads == [(PurePosixPath("/home/deploy/build.zip"), download_file)]


def test_remote_session_routes_file_management_operations() -> None:
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )
    client = FakeRemoteClient(entries={}, home=PurePosixPath("/home/deploy"))
    session = RemoteSession(site=site, client=client)

    session.delete_path(PurePosixPath("/home/deploy/app.txt"), is_dir=False)
    session.delete_path(PurePosixPath("/home/deploy/old"), is_dir=True)
    session.make_directory(PurePosixPath("/home/deploy/new-dir"))
    session.create_file(PurePosixPath("/home/deploy/new.txt"))

    assert client.deletes == [
        (PurePosixPath("/home/deploy/app.txt"), False),
        (PurePosixPath("/home/deploy/old"), True),
    ]
    assert client.directories == [PurePosixPath("/home/deploy/new-dir")]
    assert client.files == [PurePosixPath("/home/deploy/new.txt")]
