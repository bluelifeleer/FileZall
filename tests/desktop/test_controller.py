import threading
import time
from dataclasses import replace
from pathlib import Path, PurePosixPath

import pytest

from filezall_core.models import (
    AuthMode,
    Direction,
    LocalFileEntry,
    Protocol,
    RemoteFileEntry,
    SiteProfile,
    TransferItem,
    TransferStatus,
)
from filezall_core.agent_status import AgentStatus
from filezall_core.agent_deployment import AgentDetectionResult, AgentInstallResult
from filezall_core.resource_models import (
    CpuStats,
    MemoryStats,
    NetworkStats,
    ProcessDetail,
    ResourceSnapshot,
)
from filezall_core.resource_monitor import ResourceMonitoringUnavailable
from filezall_desktop.controller import MainWindowController, classify_connection_error


class FakeWindow:
    def __init__(self) -> None:
        self.local_entries = None
        self.local_path = None
        self.remote_entries = None
        self.monitoring_status = None
        self.resource_snapshot = None
        self.process_detail = None
        self.agent_statuses = []
        self.agent_status_models = []
        self.agent_versions = []
        self.statuses: list[str] = []
        self.logs: list[str] = []
        self.transfer_item_snapshots = []

    def set_local_entries(self, entries):
        self.local_entries = entries

    def set_local_directory_path(self, path):
        self.local_path = path

    def set_remote_entries(self, entries, path):
        self.remote_entries = (entries, path)

    def show_status(self, message: str) -> None:
        self.statuses.append(message)

    def append_log(self, message: str) -> None:
        self.logs.append(message)

    def set_monitoring_status(self, message: str) -> None:
        self.monitoring_status = message

    def set_agent_status(self, installed: bool | None) -> None:
        self.agent_statuses.append(installed)

    def set_agent_status_model(self, model) -> None:
        self.agent_status_models.append(model)

    def set_agent_version(self, version: str | None) -> None:
        self.agent_versions.append(version)

    def set_resource_snapshot(self, snapshot) -> None:
        self.resource_snapshot = snapshot

    def set_process_detail(self, detail) -> None:
        self.process_detail = detail

    def set_transfer_items(self, items) -> None:
        self.transfer_item_snapshots.append(list(items))


class FakeSession:
    def __init__(self) -> None:
        self.current_remote_path = PurePosixPath("/home/deploy")
        self.client = self
        self.uploads = []
        self.downloads = []
        self.list_calls = []
        self.captures = []
        self.renames = []
        self.deletes = []
        self.directories = []
        self.files = []
        self.fail_list = False
        self.disconnect_calls = 0
        self.directory_entries = {}
        self.remote_sizes = {}

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

    def remote_size(self, remote_path: PurePosixPath) -> int | None:
        return self.remote_sizes.get(remote_path)

    def rename(self, source_path: PurePosixPath, destination_path: PurePosixPath) -> None:
        self.renames.append((source_path, destination_path))

    def delete_path(self, path: PurePosixPath, *, is_dir: bool) -> None:
        self.deletes.append((path, is_dir))

    def make_directory(self, path: PurePosixPath) -> None:
        self.directories.append(path)

    def create_file(self, path: PurePosixPath) -> None:
        self.files.append(path)

    def list_directory(self, path: PurePosixPath):
        self.list_calls.append(path)
        if self.fail_list:
            raise RuntimeError("connection lost")
        return list(self.directory_entries.get(path, []))

    def capture(self, command: str) -> str:
        self.captures.append(command)
        return "{}"

    def disconnect(self) -> None:
        self.disconnect_calls += 1


class ConcurrentListSession(FakeSession):
    def __init__(self) -> None:
        super().__init__()
        self.active_lists = 0
        self.max_active_lists = 0
        self._list_lock = threading.Lock()

    def list_directory(self, path: PurePosixPath):
        with self._list_lock:
            self.active_lists += 1
            self.max_active_lists = max(self.max_active_lists, self.active_lists)
        try:
            time.sleep(0.05)
            return super().list_directory(path)
        finally:
            with self._list_lock:
                self.active_lists -= 1


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


class FailingCredentials(FakeCredentials):
    def get_secret(self, ref):
        raise RuntimeError("keychain denied")


class FakeQueue:
    def __init__(self) -> None:
        self.paused = []
        self.resumed = []
        self.canceled = []
        self.retried = []
        self.saved_tasks = []
        self.saved_items = []
        self.items = []

    def pause_task(self, task_id: str) -> None:
        self.paused.append(task_id)

    def resume_task(self, task_id: str) -> None:
        self.resumed.append(task_id)

    def cancel_task(self, task_id: str) -> None:
        self.canceled.append(task_id)

    def retry_failed(self, task_id: str) -> None:
        self.retried.append(task_id)

    def add_task(self, task, items) -> None:
        self.saved_tasks.append(task)
        self.saved_items.append(list(items))
        self.items.extend(items)

    def list_items(self, status=None, server_id=None):
        items = self.items
        if status is not None:
            items = [item for item in items if item.status is status]
        if server_id is not None:
            items = [item for item in items if item.server_id == server_id]
        return items

    def run_next(self, server_id: str, client=None, progress_callback=None):
        for index, item in enumerate(self.items):
            if item.server_id == server_id and item.status is TransferStatus.PENDING:
                running = replace(item, status=TransferStatus.RUNNING)
                self.items[index] = running
                if progress_callback is not None:
                    progress_callback(running)
                completed = replace(
                    item,
                    bytes_transferred=item.size_bytes,
                    status=TransferStatus.COMPLETED,
                )
                self.items[index] = completed
                if progress_callback is not None:
                    progress_callback(completed)
                return completed
        return None


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
        self.uninstall_calls = []
        self.resource_calls = []
        self.detail_calls = []
        self.signal_calls = []
        self.installed_checks = []
        self.installed = False
        self.detect_result = None
        self.detect_error = None
        self.expected_snapshot = ResourceSnapshot(
            cpu=CpuStats(percent=33.3),
            memory=MemoryStats(total_bytes=2000, used_bytes=1000, available_bytes=1000),
            disks=[],
            network=NetworkStats(rx_bytes_per_sec=3, tx_bytes_per_sec=4),
            processes=[],
        )
        self.detail = ProcessDetail(
            pid=456,
            user="deploy",
            name="agent",
            cpu_percent=1.0,
            memory_percent=2.0,
            command_line="filezall-agent",
            start_time="",
            thread_count=1,
            status="running",
        )

    def install(self, site, password, progress_callback=None):
        self.calls.append((site, password))
        if progress_callback is not None:
            progress_callback("Agent install: test progress")
        return self.result

    def uninstall(self, site, password, progress_callback=None):
        self.uninstall_calls.append((site, password))
        if progress_callback is not None:
            progress_callback("Agent uninstall: test progress")
        return self.result

    def is_agent_installed(self, site, password, progress_callback=None):
        self.installed_checks.append((site, password))
        if progress_callback is not None:
            progress_callback("Agent detection: test progress")
        return self.installed

    def detect_agent_installation(self, site, password, progress_callback=None):
        self.installed_checks.append((site, password))
        if progress_callback is not None:
            progress_callback("Agent detection: test progress")
        if self.detect_error is not None:
            raise self.detect_error
        if self.detect_result is not None:
            return self.detect_result
        return AgentDetectionResult(
            installed=self.installed,
            commands_run=1 if self.installed else 0,
        )

    def resource_snapshot(self, site, password, runner=None):
        self.resource_calls.append((site, password, runner))
        return self.expected_snapshot

    def process_detail(self, site, pid, password, runner=None):
        self.detail_calls.append((site, pid, password, runner))
        return self.detail

    def signal_process(self, site, pid, signal, password, runner=None):
        self.signal_calls.append((site, pid, signal, password, runner))


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


def test_controller_updates_local_directory_path_after_load(tmp_path: Path) -> None:
    window = FakeWindow()
    nested = tmp_path / "one" / "two" / "three"
    nested.mkdir(parents=True)
    controller = MainWindowController(
        window=window,
        local_lister=lambda path: [],
        session_factory=lambda site: FakeSession(),
    )

    controller.load_local_directory(nested)

    assert window.local_path == nested


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


def test_controller_reports_keychain_lookup_failure_for_saved_site() -> None:
    window = FakeWindow()
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
    controller = MainWindowController(
        window=window,
        local_lister=lambda path: [],
        session_factory=lambda site: FakeSession(),
        credential_service=FailingCredentials(),
    )

    with pytest.raises(RuntimeError, match="Enter the server password manually"):
        controller.connect(site)


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


def test_controller_reuses_cached_remote_directory_entries() -> None:
    window = FakeWindow()
    session = FakeSession()
    first_entry = RemoteFileEntry(
        path=PurePosixPath("/home/deploy/releases/v1"),
        name="v1",
        is_dir=True,
        size_bytes=0,
        modified_time=None,
    )
    session.directory_entries[PurePosixPath("/home/deploy/releases")] = [first_entry]
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
    )

    controller.connect(site, password="secret")
    controller.list_remote_directory(PurePosixPath("/home/deploy/releases"))
    session.directory_entries[PurePosixPath("/home/deploy/releases")] = []
    controller.list_remote_directory(PurePosixPath("/home/deploy/releases"))

    assert session.list_calls == [PurePosixPath("/home/deploy/releases")]
    assert window.remote_entries == ([first_entry], PurePosixPath("/home/deploy/releases"))


def test_controller_force_refresh_bypasses_remote_directory_cache() -> None:
    window = FakeWindow()
    session = FakeSession()
    stale_entry = RemoteFileEntry(
        path=PurePosixPath("/home/deploy/releases/v1"),
        name="v1",
        is_dir=True,
        size_bytes=0,
        modified_time=None,
    )
    fresh_entry = RemoteFileEntry(
        path=PurePosixPath("/home/deploy/releases/v2"),
        name="v2",
        is_dir=True,
        size_bytes=0,
        modified_time=None,
    )
    remote_path = PurePosixPath("/home/deploy/releases")
    session.directory_entries[remote_path] = [stale_entry]
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
    )

    controller.connect(site, password="secret")
    controller.load_remote_directory(remote_path)
    session.directory_entries[remote_path] = [fresh_entry]
    entries, loaded_path, _status = controller.load_remote_directory(remote_path, force_refresh=True)

    assert entries == [fresh_entry]
    assert loaded_path == remote_path
    assert session.list_calls == [remote_path, remote_path]


def test_controller_remote_mutations_invalidate_cached_directories(tmp_path: Path) -> None:
    window = FakeWindow()
    session = FakeSession()
    remote_path = PurePosixPath("/home/deploy/releases")
    stale_entry = RemoteFileEntry(
        path=remote_path / "old.txt",
        name="old.txt",
        is_dir=False,
        size_bytes=1,
        modified_time=None,
    )
    fresh_entry = RemoteFileEntry(
        path=remote_path / "new.txt",
        name="new.txt",
        is_dir=False,
        size_bytes=1,
        modified_time=None,
    )
    session.directory_entries[remote_path] = [stale_entry]
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
    )

    controller.connect(site, password="secret")
    controller.list_remote_directory(remote_path)
    session.directory_entries[remote_path] = [fresh_entry]
    local_file = tmp_path / "new.txt"
    local_file.write_text("fresh", encoding="utf-8")

    controller.upload_file(local_file, remote_path / "new.txt")
    controller.list_remote_directory(remote_path)

    assert session.uploads == [(local_file, remote_path / "new.txt")]
    assert session.list_calls == [remote_path, remote_path]
    assert window.remote_entries == ([fresh_entry], remote_path)


def test_controller_upload_file_adds_pending_item_and_updates_transfer_list(
    tmp_path: Path,
) -> None:
    window = FakeWindow()
    session = FakeSession()
    queue = FakeQueue()
    controller = MainWindowController(
        window=window,
        local_lister=lambda path: [],
        session_factory=lambda site: session,
        queue_service=queue,
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
    local_file = tmp_path / "local.txt"
    local_file.write_bytes(b"queued")

    controller.connect(site, password="secret")
    controller.upload_file(local_file, PurePosixPath("/home/deploy/local.txt"))

    assert session.uploads == []
    assert queue.saved_tasks[0].source_path == tmp_path
    assert queue.saved_tasks[0].destination_path == PurePosixPath("/home/deploy")
    pending = window.transfer_item_snapshots[0][0]
    running = window.transfer_item_snapshots[1][0]
    completed = window.transfer_item_snapshots[-1][0]
    assert pending.source_path == local_file
    assert pending.destination_path == PurePosixPath("/home/deploy/local.txt")
    assert pending.size_bytes == 6
    assert pending.status is TransferStatus.PENDING
    assert pending.bytes_transferred == 0
    assert running.status is TransferStatus.RUNNING
    assert completed.status is TransferStatus.COMPLETED
    assert completed.bytes_transferred == 6


def test_controller_download_file_adds_pending_item_and_updates_transfer_list(
    tmp_path: Path,
) -> None:
    window = FakeWindow()
    session = FakeSession()
    queue = FakeQueue()
    controller = MainWindowController(
        window=window,
        local_lister=lambda path: [],
        session_factory=lambda site: session,
        queue_service=queue,
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
    session.remote_sizes[PurePosixPath("/home/deploy/app.log")] = 9
    controller.download_file(PurePosixPath("/home/deploy/app.log"), tmp_path / "app.log")

    assert session.downloads == []
    task = queue.saved_tasks[0]
    pending = window.transfer_item_snapshots[0][0]
    running = window.transfer_item_snapshots[1][0]
    completed = window.transfer_item_snapshots[-1][0]
    assert task.direction is Direction.DOWNLOAD
    assert task.source_path == PurePosixPath("/home/deploy")
    assert task.destination_path == tmp_path
    assert pending.source_path == PurePosixPath("/home/deploy/app.log")
    assert pending.destination_path == tmp_path / "app.log"
    assert pending.size_bytes == 9
    assert pending.status is TransferStatus.PENDING
    assert running.status is TransferStatus.RUNNING
    assert completed.status is TransferStatus.COMPLETED


def test_controller_queues_recursive_directory_upload(tmp_path: Path) -> None:
    window = FakeWindow()
    session = FakeSession()
    queue = FakeQueue()
    controller = MainWindowController(
        window=window,
        local_lister=lambda path: [],
        session_factory=lambda site: session,
        queue_service=queue,
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
    root = tmp_path / "site"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_bytes(b"hello")
    (root / "assets" / "app.js").write_bytes(b"abcdef")

    controller.connect(site, password="secret")
    controller.upload_file(root, PurePosixPath("/home/deploy/site"))

    task = queue.saved_tasks[0]
    items = queue.saved_items[0]
    assert task.source_path == root
    assert task.destination_path == PurePosixPath("/home/deploy/site")
    assert task.direction is Direction.UPLOAD
    assert [(item.source_path, item.destination_path, item.size_bytes) for item in items] == [
        (root / "assets" / "app.js", PurePosixPath("/home/deploy/site/assets/app.js"), 6),
        (root / "index.html", PurePosixPath("/home/deploy/site/index.html"), 5),
    ]
    assert window.statuses[-1] == "Queued directory upload site: 2 files, 11 bytes"


def test_controller_heartbeat_checks_current_remote_directory() -> None:
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
    )

    controller.connect(site, password="secret")
    assert controller.heartbeat() is True
    session.fail_list = True
    assert controller.heartbeat() is False
    assert session.list_calls == [PurePosixPath("/home/deploy"), PurePosixPath("/home/deploy")]


def test_controller_serializes_heartbeat_and_remote_directory_loads() -> None:
    window = FakeWindow()
    session = ConcurrentListSession()
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
    )
    controller.connect(site, password="secret")
    start = threading.Barrier(3)
    errors = []

    def run_heartbeat() -> None:
        start.wait()
        try:
            controller.heartbeat()
        except Exception as exc:  # pragma: no cover - test failure aid.
            errors.append(exc)

    def run_directory_load() -> None:
        start.wait()
        try:
            controller.load_remote_directory(PurePosixPath("/home/deploy/releases"), force_refresh=True)
        except Exception as exc:  # pragma: no cover - test failure aid.
            errors.append(exc)

    heartbeat_thread = threading.Thread(target=run_heartbeat)
    directory_thread = threading.Thread(target=run_directory_load)
    heartbeat_thread.start()
    directory_thread.start()
    start.wait()
    heartbeat_thread.join(timeout=2)
    directory_thread.join(timeout=2)

    assert errors == []
    assert session.max_active_lists == 1


def test_controller_disconnects_active_session_and_clears_state() -> None:
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
    )

    controller.connect(site, password="secret")
    controller.disconnect()

    assert session.disconnect_calls == 1
    assert window.statuses[-1] == "Disconnected"
    assert controller.heartbeat() is False


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


def test_controller_detects_agent_installation_after_connecting() -> None:
    window = FakeWindow()
    service = FakeAgentInstallService(AgentInstallResult(success=True, commands_run=8))
    service.installed = True
    session = FakeSession()
    controller = MainWindowController(
        window=window,
        local_lister=lambda path: [],
        session_factory=lambda site: session,
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

    assert service.installed_checks == [(site, "secret")]
    assert window.agent_statuses == [None, True]


def test_controller_uses_detected_agent_token_for_resource_monitoring() -> None:
    window = FakeWindow()
    service = FakeAgentInstallService(AgentInstallResult(success=True, commands_run=8))
    service.detect_result = AgentDetectionResult(
        installed=True,
        commands_run=1,
        agent_token_ref="site-1:agent-token",
        agent_version="0.1.0",
    )
    session = FakeSession()
    controller = MainWindowController(
        window=window,
        local_lister=lambda path: [],
        session_factory=lambda site: session,
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

    assert controller._connected_site.agent_enabled is True
    assert controller._connected_site.agent_token_ref == "site-1:agent-token"
    assert service.resource_calls == [(controller._connected_site, "secret", session)]
    assert window.resource_snapshot == service.expected_snapshot
    assert window.agent_versions == ["0.1.0"]


def test_controller_maps_agent_detection_to_status_view_model() -> None:
    window = FakeWindow()
    service = FakeAgentInstallService(AgentInstallResult(success=True, commands_run=8))
    service.detect_result = AgentDetectionResult(
        installed=True,
        commands_run=1,
        agent_token_ref="site-1:agent-token",
        agent_version="0.0.1",
    )
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

    assert window.agent_status_models[0].state is AgentStatus.UNKNOWN
    assert window.agent_status_models[-1].state is AgentStatus.OUTDATED
    assert window.agent_status_models[-1].version == "0.0.1"
    assert window.agent_status_models[-1].primary_action == "Update Agent"


def test_controller_skips_agent_detection_for_ftp_connection() -> None:
    window = FakeWindow()
    service = FakeAgentInstallService(AgentInstallResult(success=True, commands_run=8))
    controller = MainWindowController(
        window=window,
        local_lister=lambda path: [],
        session_factory=lambda site: FakeSession(),
        agent_install_service=service,
    )
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="ftp.example.com",
        port=21,
        protocol=Protocol.FTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )

    controller.connect(site, password="secret")

    assert service.installed_checks == []
    assert window.agent_statuses == []


def test_controller_classifies_agent_detection_errors() -> None:
    window = FakeWindow()
    service = FakeAgentInstallService(AgentInstallResult(success=True, commands_run=8))
    service.detect_error = RuntimeError("System has not been booted with systemd as init system")
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

    assert any(
        "Agent detection failed: This server does not appear to support systemd" in log
        for log in window.logs
    )
    assert window.agent_statuses == [None, False]


def test_controller_classifies_connection_errors() -> None:
    assert classify_connection_error("Authentication failed") == (
        "Authentication failed. Check the username, password, SSH key, or passphrase."
    )
    assert classify_connection_error("Unable to connect to port 22: Connection refused") == (
        "Could not reach the server or port. Check the host, port, firewall, and network."
    )
    assert classify_connection_error("Permission denied while opening directory") == (
        "Permission denied. Check the account permissions for the selected remote path."
    )
    assert classify_connection_error("System has not been booted with systemd as init system") == (
        "This server does not appear to support systemd. FileZall Agent currently requires "
        "a systemd-based Linux host."
    )
    assert classify_connection_error("Agent token is not available for this site") == (
        "FileZall Agent is not installed or its token is missing. Install or update the Agent."
    )
    assert classify_connection_error("Agent install: health check failed") == (
        "FileZall Agent service started, but the health endpoint did not respond. Check "
        "firewall rules, localhost access, and filezall-agent service logs."
    )
    assert classify_connection_error("boom") == "boom"


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


def test_controller_renames_local_and_remote_paths(tmp_path: Path) -> None:
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
    )
    local_source = tmp_path / "app.txt"
    local_destination = tmp_path / "renamed.txt"
    local_source.write_text("hello", encoding="utf-8")

    controller.connect(site, password="secret")
    controller.rename_path(local_source, local_destination, remote=False)
    controller.rename_path(
        PurePosixPath("/home/deploy/app.txt"),
        PurePosixPath("/home/deploy/renamed.txt"),
        remote=True,
    )

    assert not local_source.exists()
    assert local_destination.read_text(encoding="utf-8") == "hello"
    assert session.renames == [
        (PurePosixPath("/home/deploy/app.txt"), PurePosixPath("/home/deploy/renamed.txt"))
    ]
    assert "Renamed local path" in window.statuses[-2]
    assert "Renamed remote path" in window.statuses[-1]


def test_controller_manages_local_and_remote_paths(tmp_path: Path) -> None:
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
    )
    local_file = tmp_path / "app.txt"
    local_file.write_text("hello", encoding="utf-8")
    local_dir = tmp_path / "old"
    local_dir.mkdir()

    controller.connect(site, password="secret")
    controller.delete_path(local_file, remote=False, is_dir=False)
    controller.delete_path(local_dir, remote=False, is_dir=True)
    controller.create_directory(tmp_path, remote=False)
    controller.create_file(tmp_path, remote=False)
    controller.delete_path(PurePosixPath("/home/deploy/app.txt"), remote=True, is_dir=False)
    controller.delete_path(PurePosixPath("/home/deploy/old"), remote=True, is_dir=True)
    controller.create_directory(PurePosixPath("/home/deploy"), remote=True)
    controller.create_file(PurePosixPath("/home/deploy"), remote=True)

    assert not local_file.exists()
    assert not local_dir.exists()
    assert (tmp_path / "New Folder").is_dir()
    assert (tmp_path / "New File.txt").read_bytes() == b""
    assert session.deletes == [
        (PurePosixPath("/home/deploy/app.txt"), False),
        (PurePosixPath("/home/deploy/old"), True),
    ]
    assert session.directories == [PurePosixPath("/home/deploy/New Folder")]
    assert session.files == [PurePosixPath("/home/deploy/New File.txt")]
    assert "Created remote file" in window.statuses[-1]


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
    result = controller.install_agent_with_progress()
    controller.complete_agent_install(result)

    assert service.calls == [(site, "secret")]
    assert window.statuses[-1] == "Agent installed and verified"


def test_controller_refreshes_resources_through_installed_agent_when_no_monitor_service() -> None:
    window = FakeWindow()
    service = FakeAgentInstallService(
        AgentInstallResult(
            success=True,
            commands_run=8,
            verified=True,
            agent_token_ref="site-1:agent-token",
        )
    )
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
    result = controller.install_agent_with_progress()
    controller.complete_agent_install(result)
    controller.refresh_resources()
    controller.show_process_detail(456)

    assert service.resource_calls == [(controller._connected_site, "secret", controller._session.client)]
    assert window.resource_snapshot == service.expected_snapshot
    assert service.detail_calls == [
        (controller._connected_site, 456, "secret", controller._session.client)
    ]
    assert window.process_detail == service.detail


def test_controller_stops_and_restarts_process_through_installed_agent() -> None:
    window = FakeWindow()
    service = FakeAgentInstallService(
        AgentInstallResult(
            success=True,
            commands_run=8,
            verified=True,
            agent_token_ref="site-1:agent-token",
        )
    )
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
    result = controller.install_agent_with_progress()
    controller.complete_agent_install(result)
    controller.stop_process(456)
    controller.restart_process(456)

    assert service.signal_calls == [
        (controller._connected_site, 456, "TERM", "secret", controller._session.client),
        (controller._connected_site, 456, "HUP", "secret", controller._session.client),
    ]
    assert window.statuses[-2:] == [
        "Stop signal sent to process 456",
        "Restart signal sent to process 456",
    ]


def test_controller_uninstalls_agent_for_connected_site() -> None:
    window = FakeWindow()
    service = FakeAgentInstallService(AgentInstallResult(success=True, commands_run=4, verified=True))
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
    result = controller.uninstall_agent_with_progress()
    controller.complete_agent_uninstall(result)

    assert service.uninstall_calls == [(site, "secret")]
    assert window.statuses[-1] == "Agent uninstalled"


def test_controller_does_not_expose_sync_agent_action_wrappers() -> None:
    controller = MainWindowController(
        window=FakeWindow(),
        local_lister=lambda path: [],
        session_factory=lambda site: FakeSession(),
        agent_install_service=FakeAgentInstallService(
            AgentInstallResult(success=True, commands_run=1, verified=True)
        ),
    )

    assert not hasattr(controller, "install_agent")
    assert not hasattr(controller, "uninstall_agent")
