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


class FakeRepository:
    def __init__(self, sites=None) -> None:
        self.sites = sites or []
        self.saved = []

    def list(self):
        return self.sites

    def save(self, site):
        self.saved.append(site)


class FakeCredentials:
    def __init__(self) -> None:
        self.saved = []

    def save_secret(self, site_id: str, purpose: str, secret: str) -> str:
        self.saved.append((site_id, purpose, secret))
        return f"{site_id}:{purpose}"

    def get_secret(self, ref):
        return None


class FakeQueue:
    def __init__(self) -> None:
        self.paused = []
        self.resumed = []
        self.canceled = []
        self.retried = []

    def pause_task(self, task_id: str) -> None:
        self.paused.append(task_id)

    def resume_task(self, task_id: str) -> None:
        self.resumed.append(task_id)

    def cancel_task(self, task_id: str) -> None:
        self.canceled.append(task_id)

    def retry_failed(self, task_id: str) -> None:
        self.retried.append(task_id)


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


def test_controller_loads_saved_sites_into_window() -> None:
    window = FakeWindow()
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )
    window.set_site_profiles = lambda sites: setattr(window, "sites", sites)
    controller = MainWindowController(
        window=window,
        local_lister=lambda path: [],
        session_factory=lambda site: FakeSession(),
        site_repository=FakeRepository([site]),
    )

    controller.load_saved_sites()

    assert window.sites == [site]


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


def test_controller_saves_site_and_secret_before_connecting() -> None:
    window = FakeWindow()
    session = FakeSession()
    repository = FakeRepository()
    credentials = FakeCredentials()
    controller = MainWindowController(
        window=window,
        local_lister=lambda path: [],
        session_factory=lambda site: session,
        site_repository=repository,
        credential_service=credentials,
    )
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )

    controller.connect(site, password="secret")

    assert credentials.saved == [("site-1", "password", "secret")]
    assert repository.saved[0].credential_ref == "site-1:password"
    assert session.password == "secret"


def test_controller_delegates_transfer_queue_actions() -> None:
    window = FakeWindow()
    queue = FakeQueue()
    controller = MainWindowController(
        window=window,
        local_lister=lambda path: [],
        session_factory=lambda site: FakeSession(),
        queue_service=queue,
    )

    controller.pause_transfer("task-1")
    controller.resume_transfer("task-1")
    controller.cancel_transfer("task-1")
    controller.retry_transfer("task-1")

    assert queue.paused == ["task-1"]
    assert queue.resumed == ["task-1"]
    assert queue.canceled == ["task-1"]
    assert queue.retried == ["task-1"]
