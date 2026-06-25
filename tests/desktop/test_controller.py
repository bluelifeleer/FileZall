from pathlib import Path, PurePosixPath

from filezall_core.models import AuthMode, LocalFileEntry, Protocol, RemoteFileEntry, SiteProfile
from filezall_core.agent_deployment import AgentInstallResult
from filezall_core.resource_models import (
    CpuStats,
    MemoryStats,
    NetworkStats,
    ProcessDetail,
    ResourceSnapshot,
)
from filezall_core.resource_monitor import ResourceMonitoringUnavailable
from filezall_desktop.controller import MainWindowController


class FakeWindow:
    def __init__(self) -> None:
        self.local_entries = None
        self.remote_entries = None
        self.monitoring_status = None
        self.resource_snapshot = None
        self.process_detail = None
        self.statuses: list[str] = []

    def set_local_entries(self, entries):
        self.local_entries = entries

    def set_remote_entries(self, entries, path):
        self.remote_entries = (entries, path)

    def show_status(self, message: str) -> None:
        self.statuses.append(message)

    def set_monitoring_status(self, message: str) -> None:
        self.monitoring_status = message

    def set_resource_snapshot(self, snapshot) -> None:
        self.resource_snapshot = snapshot

    def set_process_detail(self, detail) -> None:
        self.process_detail = detail


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
    def __init__(self, secrets=None) -> None:
        self.saved = []
        self.secrets = secrets or {}

    def save_secret(self, site_id: str, purpose: str, secret: str) -> str:
        self.saved.append((site_id, purpose, secret))
        return f"{site_id}:{purpose}"

    def get_secret(self, ref):
        return self.secrets.get(ref)


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


class FakeResourceMonitor:
    def __init__(self) -> None:
        self.snapshot_sites = []
        self.detail_calls = []
        self.expected_snapshot = ResourceSnapshot(
            cpu=CpuStats(percent=12.5),
            memory=MemoryStats(total_bytes=1000, used_bytes=400, available_bytes=600),
            disks=[],
            network=NetworkStats(rx_bytes_per_sec=1, tx_bytes_per_sec=2),
            processes=[],
        )
        self.detail = ProcessDetail(
            pid=123,
            user="deploy",
            name="python",
            cpu_percent=1.5,
            memory_percent=2.5,
            command_line="python app.py",
            start_time="2026-06-25T12:00:00Z",
            thread_count=8,
            status="sleeping",
        )

    def snapshot(self, site):
        self.snapshot_sites.append(site)
        return self.expected_snapshot

    def process_detail(self, site, pid: int):
        self.detail_calls.append((site, pid))
        return self.detail


class UnavailableResourceMonitor:
    def snapshot(self, site):
        raise ResourceMonitoringUnavailable("Resource monitoring requires SSH or FileZall Agent.")


class FakeAgentInstallService:
    def __init__(self, result: AgentInstallResult) -> None:
        self.result = result
        self.calls = []

    def install(self, site, password):
        self.calls.append((site, password))
        return self.result


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
    window.set_site_profiles = lambda sites, secret_lookup=None: setattr(window, "sites", sites)
    controller = MainWindowController(
        window=window,
        local_lister=lambda path: [],
        session_factory=lambda site: FakeSession(),
        site_repository=FakeRepository([site]),
    )

    controller.load_saved_sites()

    assert window.sites == [site]


def test_controller_loads_saved_sites_with_secret_lookup() -> None:
    window = FakeWindow()
    captured = {}
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
        credential_ref="site-1:password",
    )
    window.set_site_profiles = lambda sites, secret_lookup=None: captured.update(
        {"sites": sites, "secret": secret_lookup(sites[0]) if secret_lookup else None}
    )
    controller = MainWindowController(
        window=window,
        local_lister=lambda path: [],
        session_factory=lambda site: FakeSession(),
        site_repository=FakeRepository([site]),
        credential_service=FakeCredentials({"site-1:password": "remembered-secret"}),
    )

    controller.load_saved_sites()

    assert captured == {"sites": [site], "secret": "remembered-secret"}


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


def test_controller_skips_site_and_secret_save_when_not_remembering() -> None:
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

    controller.connect(site, password="secret", remember_secret=False)

    assert credentials.saved == []
    assert repository.saved == []
    assert session.password == "secret"


def test_controller_reports_monitoring_degradation_for_ftp() -> None:
    window = FakeWindow()
    controller = MainWindowController(
        window=window,
        local_lister=lambda path: [],
        session_factory=lambda site: FakeSession(),
    )
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=21,
        protocol=Protocol.FTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )

    controller.connect(site, password="secret")

    assert window.monitoring_status == "Resource monitoring requires SSH or FileZall Agent."


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


def test_controller_refreshes_resources_for_connected_site() -> None:
    window = FakeWindow()
    session = FakeSession()
    resource_monitor = FakeResourceMonitor()
    controller = MainWindowController(
        window=window,
        local_lister=lambda path: [],
        session_factory=lambda site: session,
        resource_monitor_service=resource_monitor,
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
    controller.refresh_resources()
    controller.show_process_detail(123)

    assert resource_monitor.snapshot_sites == [site]
    assert window.resource_snapshot == resource_monitor.expected_snapshot
    assert resource_monitor.detail_calls == [(site, 123)]
    assert window.process_detail == resource_monitor.detail


def test_controller_reports_resource_monitoring_unavailable() -> None:
    window = FakeWindow()
    controller = MainWindowController(
        window=window,
        local_lister=lambda path: [],
        session_factory=lambda site: FakeSession(),
        resource_monitor_service=UnavailableResourceMonitor(),
    )
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=21,
        protocol=Protocol.FTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )

    controller.connect(site, password="secret")
    controller.refresh_resources()

    assert window.statuses[-1] == "Resource monitoring requires SSH or FileZall Agent."


def test_controller_installs_agent_for_connected_site() -> None:
    window = FakeWindow()
    service = FakeAgentInstallService(AgentInstallResult(success=True, commands_run=8, verified=True))
    controller = MainWindowController(
        window=window,
        local_lister=lambda path: [],
        session_factory=lambda site: FakeSession(),
        agent_install_service=service,
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
    controller.install_agent()

    assert service.calls == [(site, "secret")]
    assert window.statuses[-1] == "Agent installed and verified"
