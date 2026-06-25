from pathlib import Path, PurePosixPath
from datetime import UTC, datetime

from filezall_desktop.main_window import MainWindow
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QSplitter, QTableWidgetSelectionRange

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
        self.deleted = []
        self.queued = []
        self.created_dirs = []
        self.created_files = []
        self.paused = []
        self.resumed = []
        self.canceled = []
        self.retried = []
        self.resource_refreshes = 0
        self.process_details = []
        self.agent_installs = 0
        self.heartbeat_results = []

    def load_saved_sites(self) -> None:
        self.loaded_sites = True

    def connect(self, site, password=None, remember_secret: bool = True) -> None:
        self.connect_calls.append((site, password, remember_secret))

    def load_local_directory(self, path) -> None:
        self.local_refreshes.append(path)

    def list_remote_directory(self, path) -> None:
        self.remote_refreshes.append(path)

    def upload_file(self, local_path, remote_path) -> None:
        self.uploads.append((local_path, remote_path))

    def download_file(self, remote_path, local_path) -> None:
        self.downloads.append((remote_path, local_path))

    def delete_path(self, path, remote: bool) -> None:
        self.deleted.append((path, remote))

    def add_to_queue(self, source_path, destination_path, direction) -> None:
        self.queued.append((source_path, destination_path, direction))

    def create_directory(self, path, remote: bool) -> None:
        self.created_dirs.append((path, remote))

    def create_file(self, path, remote: bool) -> None:
        self.created_files.append((path, remote))

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

    def install_agent(self) -> None:
        self.agent_installs += 1

    def secret_for_site(self, site):
        return None

    def heartbeat(self) -> bool:
        return self.heartbeat_results.pop(0) if self.heartbeat_results else True


class FailingConnectController(FakeController):
    def connect(self, site, password=None, remember_secret: bool = True) -> None:
        super().connect(site, password, remember_secret)
        raise RuntimeError("connect failed")


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
    assert window.connection_bar.install_agent_button.text() == "Install Agent"
    assert window.local_panel.title.text() == "Local Files"
    assert window.remote_panel.title.text() == "Remote Files"
    assert window.local_panel.action_button.text() == "Upload"
    assert window.remote_panel.action_button.text() == "Download"
    assert window.local_panel.transfer_action.text() == "Upload"
    assert window.remote_panel.transfer_action.text() == "Download"
    assert window.local_panel.path_button.maximumWidth() <= 32
    assert window.remote_panel.path_button.maximumWidth() <= 32
    assert window.transfer_table.columnCount() == 5


def test_main_window_install_agent_button_confirms_before_controller_call(qtbot) -> None:
    controller = FakeController()
    window = MainWindow(
        controller=controller,
        agent_install_confirmer=lambda _parent: True,
    )
    qtbot.addWidget(window)

    qtbot.mouseClick(window.connection_bar.install_agent_button, Qt.MouseButton.LeftButton)

    assert controller.agent_installs == 1


def test_main_window_uses_draggable_splitters_for_major_regions(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.main_splitter.count() == 3
    assert window.file_splitter.count() == 2


def test_file_panels_use_full_row_selection_for_actions(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)
    window.local_panel.set_entries(
        [
            type(
                "Entry",
                (),
                {
                    "name": "src",
                    "is_dir": True,
                    "size_bytes": 0,
                    "modified_time": None,
                },
            )()
        ]
    )

    assert window.local_panel.table.selectionBehavior() == QAbstractItemView.SelectionBehavior.SelectRows
    assert window.local_panel.table.selectionMode() == QAbstractItemView.SelectionMode.ExtendedSelection
    assert window.local_panel.table.editTriggers() == QAbstractItemView.EditTrigger.NoEditTriggers
    assert window.local_panel.table.hasMouseTracking()
    window.local_panel.table.set_hovered_row(1)
    assert window.local_panel.table.hovered_row == 1

    window.local_panel.table.setCurrentCell(1, 2)

    assert window.local_panel.selected_name() == "src"
    assert window.local_panel.selected_is_dir() is True
    assert window.local_panel.table.item(1, 2).data(Qt.ItemDataRole.UserRole) is True


def test_file_panel_ctrl_a_and_drag_style_multiselect_batch_actions(qtbot, tmp_path) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    local_root = tmp_path / "local"
    local_root.mkdir()
    window.local_panel.path_edit.setText(str(local_root))
    window.remote_panel.path_edit.setText("/home/deploy")
    window.local_panel.set_entries(
        [
            type(
                "Entry",
                (),
                {"name": "a.txt", "is_dir": False, "size_bytes": 1, "modified_time": None},
            )(),
            type(
                "Entry",
                (),
                {"name": "b.txt", "is_dir": False, "size_bytes": 1, "modified_time": None},
            )(),
        ]
    )

    window.local_panel.table.selectAll()
    qtbot.mouseClick(window.local_panel.action_button, Qt.MouseButton.LeftButton)
    window.local_panel.table.clearSelection()
    window.local_panel.table.setRangeSelected(QTableWidgetSelectionRange(1, 0, 2, 3), True)
    window.local_panel.queue_action.trigger()

    assert controller.uploads == [
        (local_root / "a.txt", PurePosixPath("/home/deploy/a.txt")),
        (local_root / "b.txt", PurePosixPath("/home/deploy/b.txt")),
    ]
    assert controller.queued == [
        (local_root / "a.txt", PurePosixPath("/home/deploy/a.txt"), Direction.UPLOAD),
        (local_root / "b.txt", PurePosixPath("/home/deploy/b.txt"), Direction.UPLOAD),
    ]


def test_context_transfer_actions_upload_and_download_selected_rows(qtbot, tmp_path) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    local_root = tmp_path / "local"
    local_root.mkdir()
    window.local_panel.path_edit.setText(str(local_root))
    window.remote_panel.path_edit.setText("/home/deploy")
    window.local_panel.set_entries(
        [
            type(
                "Entry",
                (),
                {"name": "upload.txt", "is_dir": False, "size_bytes": 1, "modified_time": None},
            )(),
        ]
    )
    window.remote_panel.set_entries(
        [
            type(
                "Entry",
                (),
                {"name": "download.txt", "is_dir": False, "size_bytes": 1, "modified_time": None},
            )(),
        ]
    )

    window.local_panel.table.selectRow(1)
    window.local_panel.transfer_action.trigger()
    window.remote_panel.table.selectRow(1)
    window.remote_panel.transfer_action.trigger()

    assert controller.uploads == [
        (local_root / "upload.txt", PurePosixPath("/home/deploy/upload.txt"))
    ]
    assert controller.downloads == [
        (PurePosixPath("/home/deploy/download.txt"), local_root / "download.txt")
    ]


def test_main_window_double_clicks_directory_rows_from_any_column(qtbot, tmp_path) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    local_root = tmp_path / "local"
    local_root.mkdir()
    window.local_panel.path_edit.setText(str(local_root))
    window.local_panel.set_entries(
        [
            type(
                "Entry",
                (),
                {
                    "name": "src",
                    "is_dir": True,
                    "size_bytes": 0,
                    "modified_time": None,
                },
            )()
        ]
    )

    window.local_panel.table.cellDoubleClicked.emit(1, 2)

    assert controller.local_refreshes == [local_root / "src"]


def test_file_panels_add_parent_row_and_clicking_it_navigates_up(qtbot, tmp_path) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    local_root = tmp_path / "local" / "child"
    local_root.mkdir(parents=True)
    window.local_panel.path_edit.setText(str(local_root))
    window.local_panel.set_entries(
        [
            type(
                "Entry",
                (),
                {"name": "app.txt", "is_dir": False, "size_bytes": 1, "modified_time": None},
            )()
        ]
    )
    window.remote_panel.path_edit.setText("/home/deploy/releases")
    window.remote_panel.set_entries(
        [
            RemoteFileEntry(
                path=PurePosixPath("/home/deploy/releases/app.log"),
                name="app.log",
                is_dir=False,
                size_bytes=1,
                modified_time=None,
            )
        ]
    )

    assert window.local_panel.name_at(0) == ".."
    assert window.remote_panel.name_at(0) == ".."

    window.local_panel.table.cellClicked.emit(0, 0)
    window.remote_panel.table.cellDoubleClicked.emit(0, 0)

    assert controller.local_refreshes == [local_root.parent]
    assert [str(path) for path in controller.remote_refreshes] == ["/home/deploy"]


def test_transfer_logs_have_resizable_splitter(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)

    assert isinstance(window.transfer_splitter, QSplitter)
    assert window.transfer_splitter.orientation() == Qt.Orientation.Vertical
    assert window.transfer_splitter.count() == 2
    assert window.transfer_splitter.widget(0) is window.transfer_table
    assert window.transfer_splitter.widget(1) is window.log_view


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


def test_main_window_displays_and_exports_logs(qtbot, tmp_path) -> None:
    export_path = tmp_path / "filezall.log"
    window = MainWindow(
        controller=FakeController(),
        log_file_chooser=lambda _parent: str(export_path),
    )
    qtbot.addWidget(window)

    window.append_log("Uploaded app.txt")
    window.export_logs_action.trigger()

    assert "Uploaded app.txt" in window.log_view.toPlainText()
    assert "Uploaded app.txt" in export_path.read_text(encoding="utf-8")


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
    window.remote_panel.table.selectRow(1)

    qtbot.mouseClick(window.remote_panel.path_button, Qt.MouseButton.LeftButton)

    assert [str(path) for path in controller.remote_refreshes] == ["/home/deploy/releases"]


def test_main_window_double_clicks_directories_to_enter(qtbot, tmp_path) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    local_root = tmp_path / "local"
    local_root.mkdir()
    window.local_panel.path_edit.setText(str(local_root))
    window.local_panel.set_entries(
        [
            type(
                "Entry",
                (),
                {
                    "name": "src",
                    "is_dir": True,
                    "size_bytes": 0,
                    "modified_time": None,
                },
            )()
        ]
    )
    window.remote_panel.path_edit.setText("/home/deploy")
    window.remote_panel.set_entries(
        [
            RemoteFileEntry(
                path=PurePosixPath("/home/deploy/releases"),
                name="releases",
                is_dir=True,
                size_bytes=0,
                modified_time=None,
            )
        ]
    )

    window.local_panel.table.cellDoubleClicked.emit(1, 0)
    window.remote_panel.table.cellDoubleClicked.emit(1, 0)

    assert controller.local_refreshes == [local_root / "src"]
    assert [str(path) for path in controller.remote_refreshes] == ["/home/deploy/releases"]


def test_main_window_path_enter_loads_typed_directories(qtbot, tmp_path) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    window.local_panel.path_edit.setText(str(tmp_path))
    window.remote_panel.path_edit.setText("/var/www")

    qtbot.keyClick(window.local_panel.path_edit, Qt.Key.Key_Return)
    qtbot.keyClick(window.remote_panel.path_edit, Qt.Key.Key_Return)

    assert controller.local_refreshes == [tmp_path]
    assert [str(path) for path in controller.remote_refreshes] == ["/var/www"]


def test_file_panel_context_actions_route_to_controller(qtbot, tmp_path) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    local_root = tmp_path / "local"
    local_root.mkdir()
    window.local_panel.path_edit.setText(str(local_root))
    window.remote_panel.path_edit.setText("/home/deploy")
    window.local_panel.set_placeholder_row("app.txt")
    window.remote_panel.set_placeholder_row("remote.txt")
    window.local_panel.table.selectRow(0)
    window.remote_panel.table.selectRow(0)

    window.local_panel.queue_action.trigger()
    window.local_panel.delete_action.trigger()
    window.local_panel.create_dir_action.trigger()
    window.local_panel.create_file_action.trigger()
    window.remote_panel.queue_action.trigger()
    window.remote_panel.delete_action.trigger()

    assert controller.queued[0] == (local_root / "app.txt", PurePosixPath("/home/deploy/app.txt"), Direction.UPLOAD)
    assert controller.deleted[0] == (local_root / "app.txt", False)
    assert controller.created_dirs[0] == (local_root, False)
    assert controller.created_files[0] == (local_root, False)
    assert controller.queued[1] == (PurePosixPath("/home/deploy/remote.txt"), local_root / "remote.txt", Direction.DOWNLOAD)
    assert controller.deleted[1] == (PurePosixPath("/home/deploy/remote.txt"), True)


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

    site, password, remember_secret = controller.connect_calls[0]
    assert controller.loaded_sites is True
    assert site.host == "example.com"
    assert site.username == "deploy"
    assert str(site.default_remote_path) == "/var/www"
    assert password == "secret"
    assert remember_secret is True
    assert window.connection_state_label.text() == ""
    assert window.connection_state_label.toolTip() == "Connected"
    assert "green" in window.connection_state_label.styleSheet()


def test_main_window_connection_failure_shows_red_status(qtbot) -> None:
    controller = FailingConnectController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    window.connection_bar.host_edit.setText("example.com")
    window.connection_bar.username_edit.setText("deploy")

    qtbot.mouseClick(window.connection_bar.connect_button, Qt.MouseButton.LeftButton)

    assert window.connection_state_label.text() == ""
    assert window.connection_state_label.toolTip() == "Failed"
    assert "red" in window.connection_state_label.styleSheet()
    assert window.connection_bar.connect_button.isEnabled()


def test_main_window_logs_connection_attempt_and_failure(qtbot) -> None:
    controller = FailingConnectController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    window.connection_bar.host_edit.setText("example.com")
    window.connection_bar.port_edit.setText("2222")
    window.connection_bar.username_edit.setText("deploy")
    window.connection_bar.secret_edit.setText("secret")

    qtbot.mouseClick(window.connection_bar.connect_button, Qt.MouseButton.LeftButton)

    logs = window.log_view.toPlainText()
    assert "Connecting to example.com:2222 as deploy" in logs
    assert "Connection failed: connect failed" in logs


def test_connection_status_light_uses_tooltip_for_state_text(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)

    window._set_connection_state("Connecting", "goldenrod")

    assert window.connection_state_label.text() == ""
    assert window.connection_state_label.toolTip() == "Connecting"
    assert "goldenrod" in window.connection_state_label.styleSheet()


def test_heartbeat_updates_status_light_after_connection(qtbot) -> None:
    controller = FakeController()
    controller.heartbeat_results = [True, False]
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)

    window._handle_heartbeat_tick()
    assert window.connection_state_label.toolTip() == "Connected"
    assert "green" in window.connection_state_label.styleSheet()

    window._handle_heartbeat_tick()
    assert window.connection_state_label.toolTip() == "Disconnected"
    assert "red" in window.connection_state_label.styleSheet()


def test_heartbeat_failure_logs_once_until_recovered(qtbot) -> None:
    controller = FakeController()
    controller.heartbeat_results = [False, False, True, False]
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)

    window._handle_heartbeat_tick()
    window._handle_heartbeat_tick()
    assert window.log_view.toPlainText().count("Heartbeat failed: disconnected") == 1

    window._handle_heartbeat_tick()
    window._handle_heartbeat_tick()
    assert window.log_view.toPlainText().count("Heartbeat failed: disconnected") == 2


def test_main_window_can_connect_without_remembering_password(qtbot) -> None:
    controller = FakeController()
    window = MainWindow(
        controller=controller,
        remember_secret_confirmer=lambda _parent: False,
    )
    qtbot.addWidget(window)
    window.connection_bar.host_edit.setText("example.com")
    window.connection_bar.username_edit.setText("deploy")
    window.connection_bar.secret_edit.setText("secret")

    qtbot.mouseClick(window.connection_bar.connect_button, Qt.MouseButton.LeftButton)

    _site, _password, remember_secret = controller.connect_calls[0]
    assert remember_secret is False


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

    site, _password, _remember_secret = controller.connect_calls[0]
    assert site.protocol == Protocol.FTP


def test_main_window_displays_monitoring_status(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)

    window.set_monitoring_status("Resource monitoring requires SSH or FileZall Agent.")

    assert window.monitoring_status_label.text() == "Resource monitoring requires SSH or FileZall Agent."
    assert window.agent_status_label.text() == "Agent not installed"
    assert not window.resource_install_agent_button.isHidden()


def test_resource_agent_install_button_uses_confirmed_install_flow(qtbot) -> None:
    controller = FakeController()
    window = MainWindow(
        controller=controller,
        agent_install_confirmer=lambda _parent: True,
    )
    qtbot.addWidget(window)
    window.set_monitoring_status("Resource monitoring requires SSH or FileZall Agent.")

    qtbot.mouseClick(window.resource_install_agent_button, Qt.MouseButton.LeftButton)

    assert controller.agent_installs == 1


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

    site, password, _remember_secret = controller.connect_calls[0]
    assert site == saved_site
    assert password is None


def test_saved_site_autofills_quick_connect_fields_with_secret(qtbot, tmp_path) -> None:
    class SavedController(FakeController):
        def secret_for_site(self, site):
            return "remembered-secret"

    controller = SavedController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    saved_site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=2121,
        protocol=Protocol.FTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
        default_local_path=tmp_path,
        default_remote_path=PurePosixPath("/var/www"),
        credential_ref="site-1:password",
    )

    window.set_site_profiles([saved_site])

    assert window.connection_bar.site_selector.currentIndex() == 1
    assert window.connection_bar.host_edit.text() == "example.com"
    assert window.connection_bar.port_edit.text() == "2121"
    assert window.connection_bar.username_edit.text() == "deploy"
    assert window.connection_bar.protocol_selector.currentText() == "FTP"
    assert window.connection_bar.auth_mode_selector.currentText() == "Password"
    assert window.connection_bar.secret_edit.text() == "remembered-secret"
    assert window.local_panel.path_edit.text() == str(tmp_path)
    assert window.remote_panel.path_edit.text() == "/var/www"


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
