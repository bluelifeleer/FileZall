from pathlib import Path, PurePosixPath
from datetime import UTC, datetime

from filezall_desktop.main_window import MainWindow
from PySide6.QtCore import Qt

from filezall_core.models import (
    AuthMode,
    Direction,
    Protocol,
    RemoteFileEntry,
    SiteProfile,
    TransferItem,
    TransferStatus,
)
from filezall_core.resource_models import (
    CpuStats,
    DiskUsage,
    MemoryStats,
    NetworkStats,
    ProcessDetail,
    ProcessSummary,
    ResourceSnapshot,
)


class FakeController:
    def __init__(self) -> None:
        self.loaded_sites = False
        self.connect_calls = []
        self.local_refreshes = []
        self.remote_refreshes = []
        self.uploads = []
        self.downloads = []
        self.paused = []
        self.resumed = []
        self.canceled = []
        self.retried = []
        self.resource_refreshes = 0
        self.process_details = []

    def load_saved_sites(self) -> None:
        self.loaded_sites = True

    def connect(self, site, password=None) -> None:
        self.connect_calls.append((site, password))

    def load_local_directory(self, path) -> None:
        self.local_refreshes.append(path)

    def list_remote_directory(self, path) -> None:
        self.remote_refreshes.append(path)

    def upload_file(self, local_path, remote_path) -> None:
        self.uploads.append((local_path, remote_path))

    def download_file(self, remote_path, local_path) -> None:
        self.downloads.append((remote_path, local_path))

    def pause_transfer(self, task_id) -> None:
        self.paused.append(task_id)

    def resume_transfer(self, task_id) -> None:
        self.resumed.append(task_id)

    def cancel_transfer(self, task_id) -> None:
        self.canceled.append(task_id)

    def retry_transfer(self, task_id) -> None:
        self.retried.append(task_id)

    def refresh_resources(self) -> None:
        self.resource_refreshes += 1

    def show_process_detail(self, pid) -> None:
        self.process_details.append(pid)


def test_main_window_has_filezall_title(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "FileZall"
    assert not window.windowIcon().isNull()


def test_main_window_exposes_connection_and_file_panels(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.connection_bar.host_edit.placeholderText() == "Host"
    assert window.connection_bar.port_edit.text() == "22"
    assert window.connection_bar.auth_mode_selector.itemText(0) == "Password"
    assert window.connection_bar.auth_mode_selector.itemText(1) == "SSH Key"
    assert [
        window.connection_bar.protocol_selector.itemText(i)
        for i in range(window.connection_bar.protocol_selector.count())
    ] == ["SFTP", "FTP", "FTPS"]
    assert window.connection_bar.secret_edit.placeholderText() == "Password / passphrase"
    assert window.connection_bar.ssh_key_path_edit.placeholderText() == "SSH key path"
    assert window.local_panel.title.text() == "Local Files"
    assert window.remote_panel.title.text() == "Remote Files"
    assert window.local_panel.action_button.text() == "Upload"
    assert window.remote_panel.action_button.text() == "Download"
    assert window.local_panel.path_button.maximumWidth() <= 32
    assert window.remote_panel.path_button.maximumWidth() <= 32
    assert window.transfer_table.columnCount() == 5


def test_main_window_uses_draggable_splitters_for_major_regions(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.main_splitter.count() == 3
    assert window.file_splitter.count() == 2


def test_main_window_has_help_menu_actions(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    menus = {action.text(): action.menu() for action in window.menuBar().actions()}
    assert "Help" in menus
    help_actions = {action.text(): action for action in window.help_menu.actions()}

    assert set(help_actions) == {"About FileZall", "Version", "Protocols"}
    assert help_actions["About FileZall"].statusTip()
    assert help_actions["Version"].statusTip()
    assert help_actions["Protocols"].statusTip()


def test_main_window_local_path_button_chooses_and_loads_directory(qtbot, tmp_path) -> None:
    controller = FakeController()
    window = MainWindow(
        controller=controller,
        local_directory_chooser=lambda _parent, _current: str(tmp_path),
    )
    qtbot.addWidget(window)

    qtbot.mouseClick(window.local_panel.path_button, Qt.MouseButton.LeftButton)

    assert window.local_panel.path_edit.text() == str(tmp_path)
    assert controller.local_refreshes == [tmp_path]


def test_main_window_remote_path_button_enters_selected_directory(qtbot) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    window.remote_panel.path_edit.setText("/home/deploy")
    window.remote_panel.set_entries(
        [
            RemoteFileEntry(
                path=PurePosixPath("/home/deploy/releases"),
                name="releases",
                is_dir=True,
                size_bytes=0,
                modified_time=datetime(2026, 6, 25, tzinfo=UTC),
            )
        ]
    )
    window.remote_panel.table.selectRow(0)

    qtbot.mouseClick(window.remote_panel.path_button, Qt.MouseButton.LeftButton)

    assert [str(path) for path in controller.remote_refreshes] == ["/home/deploy/releases"]


def test_main_window_refresh_buttons_clear_current_selection(qtbot, tmp_path) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    window.local_panel.path_edit.setText(str(tmp_path))
    window.local_panel.set_placeholder_row("app.txt")
    window.local_panel.table.selectRow(0)

    qtbot.mouseClick(window.local_panel.refresh_button, Qt.MouseButton.LeftButton)

    assert window.local_panel.table.selectionModel().selectedRows() == []


def test_main_window_loads_sites_and_connects_button_to_controller(qtbot) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    window.connection_bar.host_edit.setText("example.com")
    window.connection_bar.username_edit.setText("deploy")
    window.connection_bar.secret_edit.setText("secret")
    window.remote_panel.path_edit.setText("/var/www")

    qtbot.mouseClick(window.connection_bar.connect_button, Qt.MouseButton.LeftButton)

    site, password = controller.connect_calls[0]
    assert controller.loaded_sites is True
    assert site.host == "example.com"
    assert site.username == "deploy"
    assert str(site.default_remote_path) == "/var/www"
    assert password == "secret"


def test_main_window_uses_selected_ftp_protocol_when_connecting(qtbot) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    window.connection_bar.host_edit.setText("ftp.example.com")
    window.connection_bar.port_edit.setText("21")
    window.connection_bar.username_edit.setText("deploy")
    window.connection_bar.secret_edit.setText("secret")
    window.connection_bar.protocol_selector.setCurrentText("FTP")

    qtbot.mouseClick(window.connection_bar.connect_button, Qt.MouseButton.LeftButton)

    site, _password = controller.connect_calls[0]
    assert site.protocol == Protocol.FTP


def test_main_window_displays_monitoring_status(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)

    window.set_monitoring_status("Resource monitoring requires SSH or FileZall Agent.")

    assert window.monitoring_status_label.text() == "Resource monitoring requires SSH or FileZall Agent."


def test_main_window_connects_selected_saved_site_with_stored_credential_ref(qtbot) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    saved_site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
        credential_ref="site-1:password",
    )
    window.set_site_profiles([saved_site])
    window.connection_bar.site_selector.setCurrentIndex(1)

    qtbot.mouseClick(window.connection_bar.connect_button, Qt.MouseButton.LeftButton)

    site, password = controller.connect_calls[0]
    assert site == saved_site
    assert password is None


def test_main_window_refresh_upload_and_download_buttons_call_controller(qtbot, tmp_path) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    local_root = tmp_path / "local"
    local_root.mkdir()
    (local_root / "app.txt").write_text("hello", encoding="utf-8")
    window.local_panel.path_edit.setText(str(local_root))
    window.remote_panel.path_edit.setText("/home/deploy")
    window.local_panel.set_placeholder_row("app.txt")
    window.remote_panel.set_placeholder_row("remote.txt")
    window.local_panel.table.selectRow(0)
    window.remote_panel.table.selectRow(0)

    qtbot.mouseClick(window.local_panel.refresh_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window.remote_panel.refresh_button, Qt.MouseButton.LeftButton)
    window.local_panel.table.selectRow(0)
    window.remote_panel.table.selectRow(0)
    qtbot.mouseClick(window.local_panel.action_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window.remote_panel.action_button, Qt.MouseButton.LeftButton)

    assert controller.local_refreshes == [local_root]
    assert str(controller.remote_refreshes[0]) == "/home/deploy"
    assert controller.uploads == [(local_root / "app.txt", controller.remote_refreshes[0] / "app.txt")]
    assert controller.downloads == [(controller.remote_refreshes[0] / "remote.txt", local_root / "remote.txt")]


def test_main_window_renders_transfer_rows_and_queue_action_buttons(qtbot, tmp_path) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    item = TransferItem(
        id="item-1",
        task_id="task-1",
        server_id="site-1",
        direction=Direction.UPLOAD,
        source_path=tmp_path / "app.zip",
        destination_path=PurePosixPath("/home/deploy/app.zip"),
        temporary_path=PurePosixPath("/home/deploy/.filezall.app.zip.part"),
        size_bytes=100,
        protocol=Protocol.SFTP,
        bytes_transferred=25,
        status=TransferStatus.RUNNING,
    )

    window.set_transfer_items([item])
    window.transfer_table.selectRow(0)
    qtbot.mouseClick(window.pause_transfer_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window.resume_transfer_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window.cancel_transfer_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window.retry_transfer_button, Qt.MouseButton.LeftButton)

    assert window.transfer_table.rowCount() == 1
    assert window.transfer_table.item(0, 0).text() == "site-1"
    assert window.transfer_table.item(0, 2).text() == "app.zip"
    assert window.transfer_table.item(0, 3).text() == "25%"
    assert controller.paused == ["task-1"]
    assert controller.resumed == ["task-1"]
    assert controller.canceled == ["task-1"]
    assert controller.retried == ["task-1"]


def test_main_window_renders_resource_snapshot_and_process_detail(qtbot) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    snapshot = ResourceSnapshot(
        cpu=CpuStats(percent=12.5),
        memory=MemoryStats(total_bytes=1000, used_bytes=400, available_bytes=600),
        disks=[DiskUsage(mount="/", total_bytes=2000, used_bytes=1000, available_bytes=1000)],
        network=NetworkStats(rx_bytes_per_sec=10, tx_bytes_per_sec=20),
        processes=[
            ProcessSummary(
                pid=123,
                user="deploy",
                name="python",
                cpu_percent=1.5,
                memory_percent=2.5,
            )
        ],
    )
    detail = ProcessDetail(
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

    window.set_resource_snapshot(snapshot)
    window.process_table.selectRow(0)
    qtbot.mouseClick(window.resource_refresh_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window.process_detail_button, Qt.MouseButton.LeftButton)
    window.set_process_detail(detail)

    assert window.cpu_value_label.text() == "12.5%"
    assert window.memory_value_label.text() == "400 / 1000 bytes"
    assert window.disk_value_label.text() == "/: 1000 / 2000 bytes"
    assert window.network_value_label.text() == "RX 10 B/s, TX 20 B/s"
    assert window.process_table.item(0, 0).text() == "123"
    assert controller.resource_refreshes == 1
    assert controller.process_details == [123]
    assert "python app.py" in window.process_detail_label.text()
    assert "threads: 8" in window.process_detail_label.text()
