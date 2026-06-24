from pathlib import Path, PurePosixPath

from filezall_core.models import AuthMode, LocalFileEntry, Protocol, RemoteFileEntry, SiteProfile
from filezall_desktop.controller import MainWindowController


class FakeWindow:
    def __init__(self) -> None:
        self.local_entries = None
        self.remote_entries = None
        self.statuses: list[str] = []

    def set_local_entries(self, entries):
        self.local_entries = entries

    def set_remote_entries(self, entries, path):
        self.remote_entries = (entries, path)

    def show_status(self, message: str) -> None:
        self.statuses.append(message)


class FakeSession:
    def __init__(self) -> None:
        self.current_remote_path = PurePosixPath("/home/deploy")
        self.uploads = []
        self.downloads = []

    def connect_and_list_default(self, password=None):
        self.password = password
        return [
            RemoteFileEntry(
                path=PurePosixPath("/home/deploy/app.log"),
                name="app.log",
                is_dir=False,
                size_bytes=10,
                modified_time=None,
            )
        ]

    def upload_file(self, local_path: Path, remote_path: PurePosixPath) -> None:
        self.uploads.append((local_path, remote_path))

    def download_file(self, remote_path: PurePosixPath, local_path: Path) -> None:
        self.downloads.append((remote_path, local_path))


def test_controller_loads_local_directory(tmp_path: Path) -> None:
    window = FakeWindow()
    entry = LocalFileEntry(
        path=tmp_path / "app.txt",
        name="app.txt",
        is_dir=False,
        size_bytes=5,
        modified_time=None,
    )
    controller = MainWindowController(
        window=window,
        local_lister=lambda path: [entry],
        session_factory=lambda site: FakeSession(),
    )

    controller.load_local_directory(tmp_path)

    assert window.local_entries == [entry]
    assert window.statuses[-1] == f"Loaded local directory {tmp_path}"


def test_controller_connects_remote_and_transfers_one_file(tmp_path: Path) -> None:
    window = FakeWindow()
    session = FakeSession()
    controller = MainWindowController(
        window=window,
        local_lister=lambda path: [],
        session_factory=lambda site: session,
    )
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
        default_remote_path=PurePosixPath("/home/deploy"),
    )

    controller.connect(site, password="secret")
    controller.upload_file(tmp_path / "local.txt", PurePosixPath("/home/deploy/local.txt"))
    controller.download_file(PurePosixPath("/home/deploy/app.log"), tmp_path / "app.log")

    assert window.remote_entries[1] == PurePosixPath("/home/deploy")
    assert window.remote_entries[0][0].name == "app.log"
    assert session.password == "secret"
    assert session.uploads == [(tmp_path / "local.txt", PurePosixPath("/home/deploy/local.txt"))]
    assert session.downloads == [(PurePosixPath("/home/deploy/app.log"), tmp_path / "app.log")]
