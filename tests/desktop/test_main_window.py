import json
import time
import zipfile
from pathlib import Path, PurePosixPath
from datetime import UTC, datetime

from filezall_desktop.main_window import MainWindow, ResourceUsageChart
from filezall_desktop.theme import hover_color_for_theme
from filezall_desktop.widgets import ICON_KEY_ROLE
from filezall_desktop.i18n import EN_LANGUAGE, ZH_CN_LANGUAGE, _TRANSLATIONS, t
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, QThread
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QHeaderView,
    QSplitter,
    QTableView,
    QTableWidget,
    QTableWidgetSelectionRange,
)

from filezall_core.models import (
    AuthMode,
    ConflictPolicy,
    Direction,
    Protocol,
    RemoteFileEntry,
    SiteProfile,
    TransferItem,
    TransferStatus,
)
from filezall_core.agent_status import AgentStatus, AgentStatusViewModel
from filezall_core.agent_deployment import AgentInstallResult
from filezall_core.resource_models import (
    CpuStats,
    DiskUsage,
    MemoryStats,
    NetworkStats,
    ProcessDetail,
    ProcessSummary,
    ResourceSnapshot,
)


def _use_english(window: MainWindow) -> None:
    window.english_language_action.trigger()


def _send_chart_mouse_move(chart: ResourceUsageChart, point: QPoint) -> None:
    event_point = QPointF(point)
    QApplication.sendEvent(
        chart,
        QMouseEvent(
            QEvent.Type.MouseMove,
            event_point,
            event_point,
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        ),
    )


class FakeController:
    def __init__(self) -> None:
        self.loaded_sites = False
        self.connect_calls = []
        self.local_refreshes = []
        self.remote_refreshes = []
        self.uploads = []
        self.upload_conflict_policies = []
        self.downloads = []
        self.download_conflict_policies = []
        self.deleted = []
        self.queued = []
        self.created_dirs = []
        self.created_files = []
        self.renamed = []
        self.paused = []
        self.resumed = []
        self.canceled = []
        self.retried = []
        self.resource_refreshes = 0
        self.process_details = []
        self.process_stops = []
        self.process_restarts = []
        self.agent_installs = 0
        self.agent_uninstalls = 0
        self.heartbeat_results = []
        self.disconnect_calls = 0

    def load_saved_sites(self) -> None:
        self.loaded_sites = True

    def connect(self, site, password=None, remember_secret: bool = True) -> None:
        self.connect_calls.append((site, password, remember_secret))

    def disconnect(self) -> None:
        self.disconnect_calls += 1

    def load_local_directory(self, path) -> None:
        self.local_refreshes.append(path)

    def list_remote_directory(self, path) -> None:
        self.remote_refreshes.append(path)

    def upload_file(self, local_path, remote_path, conflict_policy=None) -> None:
        self.uploads.append((local_path, remote_path))
        self.upload_conflict_policies.append(conflict_policy)

    def download_file(self, remote_path, local_path, conflict_policy=None) -> None:
        self.downloads.append((remote_path, local_path))
        self.download_conflict_policies.append(conflict_policy)

    def delete_path(self, path, remote: bool, is_dir: bool | None = None) -> None:
        self.deleted.append((path, remote, is_dir))

    def add_to_queue(self, source_path, destination_path, direction) -> None:
        self.queued.append((source_path, destination_path, direction))

    def create_directory(self, path, remote: bool) -> None:
        self.created_dirs.append((path, remote))

    def create_file(self, path, remote: bool) -> None:
        self.created_files.append((path, remote))

    def rename_path(self, source_path, destination_path, remote: bool) -> None:
        self.renamed.append((source_path, destination_path, remote))

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

    def stop_process(self, pid) -> None:
        self.process_stops.append(pid)

    def restart_process(self, pid) -> None:
        self.process_restarts.append(pid)

    def install_agent_with_progress(self, progress=None) -> AgentInstallResult:
        self.agent_installs += 1
        return AgentInstallResult(success=True, commands_run=1, verified=True)

    def complete_agent_install(self, result: AgentInstallResult) -> None:
        return None

    def uninstall_agent_with_progress(self, progress=None) -> AgentInstallResult:
        self.agent_uninstalls += 1
        return AgentInstallResult(success=True, commands_run=1, verified=True)

    def complete_agent_uninstall(self, result: AgentInstallResult) -> None:
        return None

    def secret_for_site(self, site):
        return None

    def heartbeat(self) -> bool:
        return self.heartbeat_results.pop(0) if self.heartbeat_results else True


class FakeSettings:
    def __init__(self, dismissed: bool = False) -> None:
        self.dismissed = dismissed
        self.saved = []

    def get_bool(self, key: str, default: bool = False) -> bool:
        if key == "onboarding.dismissed":
            return self.dismissed
        return default

    def set_bool(self, key: str, value: bool) -> None:
        self.saved.append((key, value))
        if key == "onboarding.dismissed":
            self.dismissed = value


class FakeSiteRepository:
    def __init__(self, sites=None) -> None:
        self.sites = list(sites or [])

    def list(self):
        return list(self.sites)

    def save(self, site) -> None:
        self.sites = [existing for existing in self.sites if existing.id != site.id]
        self.sites.append(site)

    def delete(self, site_id: str) -> None:
        self.sites = [site for site in self.sites if site.id != site_id]


class ProgressAgentController(FakeController):
    def __init__(self, delay_seconds: float = 0) -> None:
        super().__init__()
        self.delay_seconds = delay_seconds
        self.agent_install_results = []

    def install_agent_with_progress(self, progress) -> AgentInstallResult:
        self.agent_installs += 1
        progress("Agent install: uploading package")
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        progress("Agent install: health check passed")
        return AgentInstallResult(success=True, commands_run=2, verified=True)

    def complete_agent_install(self, result: AgentInstallResult) -> None:
        self.agent_install_results.append(result)


class FailingProgressAgentController(FakeController):
    def install_agent_with_progress(self, progress) -> AgentInstallResult:
        self.agent_installs += 1
        progress("Agent install: uploading package")
        raise RuntimeError("sudo password required")


class FailingConnectController(FakeController):
    def connect(self, site, password=None, remember_secret: bool = True) -> None:
        super().connect(site, password, remember_secret)
        raise RuntimeError("connect failed")


class AuthenticationFailingConnectController(FakeController):
    def connect(self, site, password=None, remember_secret: bool = True) -> None:
        super().connect(site, password, remember_secret)
        raise RuntimeError("Authentication failed")


class ObservingRemoteLoadingController(FakeController):
    def __init__(self) -> None:
        super().__init__()
        self.window = None
        self.loading_snapshot = None

    def list_remote_directory(self, path) -> None:
        self.loading_snapshot = (
            self.window.remote_panel.table.isEnabled(),
            self.window.remote_panel.refresh_button.isEnabled(),
            self.window.statusBar().currentMessage(),
        )
        super().list_remote_directory(path)


class SlowRemoteDataController(FakeController):
    def __init__(self, delay_seconds: float = 0.3) -> None:
        super().__init__()
        self.delay_seconds = delay_seconds

    def load_remote_directory(self, path):
        time.sleep(self.delay_seconds)
        entries = [
            RemoteFileEntry(
                path=path / "nested",
                name="nested",
                is_dir=True,
                size_bytes=0,
                modified_time=None,
            )
        ]
        return entries, path, f"Loaded remote directory {path}"


class SnapshotController(FakeController):
    def __init__(self) -> None:
        super().__init__()
        self.snapshot = ResourceSnapshot(
            cpu=CpuStats(percent=42.0),
            memory=MemoryStats(total_bytes=100, used_bytes=50, available_bytes=50),
            disks=[DiskUsage(mount="/", total_bytes=200, used_bytes=100, available_bytes=100)],
            network=NetworkStats(rx_bytes_per_sec=0, tx_bytes_per_sec=0),
            processes=[],
        )

    def load_resource_snapshot(self):
        self.resource_refreshes += 1
        return self.snapshot, "Resource snapshot refreshed"


class FailingSnapshotController(SnapshotController):
    def load_resource_snapshot(self):
        self.resource_refreshes += 1
        raise RuntimeError("agent timeout")


class AsyncConnectController(FakeController):
    def connect_for_window(self, site, password=None, remember_secret: bool = True):
        self.connect_calls.append((site, password, remember_secret))
        time.sleep(0.05)
        path = PurePosixPath("/home/deploy")
        return {
            "entries": [
                RemoteFileEntry(
                    path=path / "app",
                    name="app",
                    is_dir=True,
                    size_bytes=0,
                    modified_time=None,
                )
            ],
            "remote_path": path,
            "monitoring_status": "Resource snapshot refreshed",
            "agent_status": False,
            "agent_status_sequence": [None, False],
            "agent_status_message": None,
            "resource_snapshot": None,
            "resource_status": None,
            "status": "Connected to Production",
            "logs": ["Agent detection started", "Agent service not installed"],
        }


class ThreadRecordingWindow(MainWindow):
    def __init__(self, *args, **kwargs) -> None:
        self.resource_snapshot_threads = []
        self.remote_entries_threads = []
        super().__init__(*args, **kwargs)

    def set_resource_snapshot(self, snapshot):
        self.resource_snapshot_threads.append(QThread.currentThread())
        super().set_resource_snapshot(snapshot)

    def set_remote_entries(self, entries, path):
        self.remote_entries_threads.append(QThread.currentThread())
        super().set_remote_entries(entries, path)


def test_main_window_has_filezall_title(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "FileZall"
    assert not window.windowIcon().isNull()


def test_main_window_exposes_connection_and_file_panels(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    _use_english(window)

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
    assert window.local_panel.path_button.text() == "..."
    assert window.remote_panel.path_button.maximumWidth() <= 32
    assert window.transfer_table.columnCount() == 9


def test_local_path_button_keeps_ellipsis_after_language_and_theme_changes(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)

    window.dark_theme_action.trigger()
    window.chinese_language_action.trigger()
    window.light_theme_action.trigger()

    assert window.local_panel.path_button.text() == "..."
    assert window.local_panel.path_button.minimumWidth() >= 30
    assert window.local_panel.path_button.maximumWidth() <= 34
    assert window.remote_panel.path_button.text() == ">"


def test_main_window_install_agent_button_confirms_before_controller_call(qtbot) -> None:
    controller = FakeController()
    window = MainWindow(
        controller=controller,
        agent_install_confirmer=lambda _parent: True,
    )
    qtbot.addWidget(window)

    qtbot.mouseClick(window.connection_bar.install_agent_button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: controller.agent_installs == 1, timeout=3000)
    assert controller.agent_installs == 1


def test_main_window_logs_agent_install_steps(qtbot) -> None:
    controller = FakeController()
    window = MainWindow(
        controller=controller,
        agent_install_confirmer=lambda _parent: True,
    )
    qtbot.addWidget(window)

    qtbot.mouseClick(window.connection_bar.install_agent_button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(
        lambda: "Agent install command finished" in window.log_view.toPlainText(),
        timeout=3000,
    )
    logs = window.log_view.toPlainText()
    assert "Agent install requested" in logs
    assert "Agent install confirmed" in logs
    assert "Agent install command finished" in logs


def test_main_window_updates_top_agent_button_when_agent_is_installed(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)
    _use_english(window)

    window.set_agent_status(True)

    assert window.connection_bar.install_agent_button.text() == "Update Agent"

    window.set_agent_status(False)

    assert window.connection_bar.install_agent_button.text() == "Install Agent"


def test_main_window_confirms_and_logs_agent_update_when_installed(qtbot) -> None:
    controller = FakeController()
    confirmation_actions = []
    window = MainWindow(
        controller=controller,
        agent_install_confirmer=lambda _parent, action: confirmation_actions.append(action) or True,
    )
    qtbot.addWidget(window)
    window.set_agent_status(True)

    qtbot.mouseClick(window.connection_bar.install_agent_button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(
        lambda: "Agent update command finished" in window.log_view.toPlainText(),
        timeout=3000,
    )
    logs = window.log_view.toPlainText()
    assert confirmation_actions == ["update"]
    assert controller.agent_installs == 1
    assert "Agent update requested" in logs
    assert "Agent update confirmed" in logs
    assert "Agent update command finished" in logs


def test_main_window_runs_agent_install_in_background_and_logs_progress(qtbot) -> None:
    controller = ProgressAgentController(delay_seconds=0.1)
    window = MainWindow(
        controller=controller,
        agent_install_confirmer=lambda _parent: True,
    )
    qtbot.addWidget(window)

    qtbot.mouseClick(window.connection_bar.install_agent_button, Qt.MouseButton.LeftButton)

    assert not window.connection_bar.install_agent_button.isEnabled()
    qtbot.waitUntil(
        lambda: "Agent install command finished" in window.log_view.toPlainText(),
        timeout=3000,
    )

    logs = window.log_view.toPlainText()
    assert "Agent install: uploading package" in logs
    assert "Agent install: health check passed" in logs
    assert controller.agent_install_results[0].verified is True
    assert window.connection_bar.install_agent_button.isEnabled()


def test_agent_install_progress_updates_status_card(qtbot) -> None:
    controller = ProgressAgentController(delay_seconds=0.1)
    window = MainWindow(
        controller=controller,
        agent_install_confirmer=lambda _parent: True,
    )
    qtbot.addWidget(window)

    qtbot.mouseClick(window.connection_bar.install_agent_button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(
        lambda: "Agent install command finished" in window.agent_status_card.message_label.text(),
        timeout=3000,
    )

    assert [label.text() for label in window.agent_status_card.step_labels] == [
        "1. Agent install: uploading package",
        "2. Agent install: health check passed",
    ]


def test_main_window_logs_agent_install_failure_from_background(qtbot) -> None:
    controller = FailingProgressAgentController()
    window = MainWindow(
        controller=controller,
        agent_install_confirmer=lambda _parent: True,
    )
    qtbot.addWidget(window)

    qtbot.mouseClick(window.connection_bar.install_agent_button, Qt.MouseButton.LeftButton)

    expected_message = (
        "Permission denied while managing FileZall Agent. Connect as a sudo-capable user "
        "or configure passwordless sudo for Agent install commands."
    )
    qtbot.waitUntil(
        lambda: f"Agent installation failed: {expected_message}" in window.log_view.toPlainText(),
        timeout=3000,
    )

    assert f"Background operation failed [agent install]: {expected_message}" in window.log_view.toPlainText()
    assert window.connection_bar.install_agent_button.isEnabled()


def test_main_window_uses_draggable_splitters_for_major_regions(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.main_splitter.count() == 3
    assert window.file_splitter.count() == 2


def test_main_window_uses_single_unified_log_region(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)

    assert window.transfer_splitter.count() == 2
    assert window.transfer_splitter.widget(1) is window.log_viewer
    assert window.log_view is window.log_viewer
    assert not hasattr(window, "simple_log_view")

    window.append_log("Connected to Production", category="connection")
    window.append_log("Uploaded app.txt", category="transfer")

    assert "Connected to Production" in window.log_view.toPlainText()
    assert "Uploaded app.txt" in window.log_view.toPlainText()


def test_settings_menu_opens_dialog_for_theme_language_and_transfer_settings(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)
    _use_english(window)

    menu_titles = [action.text() for action in window.menuBar().actions()]
    assert "Settings" in menu_titles
    assert "Theme" not in menu_titles
    assert "Language" not in menu_titles

    window.settings_action.trigger()

    assert window.settings_dialog is not None
    assert window.settings_dialog.isVisible()
    assert window.settings_dialog.theme_selector.currentText() == "System"
    assert window.settings_dialog.language_selector.currentText() == "English"

    window.settings_dialog.theme_selector.setCurrentText("Dark")
    window.settings_dialog.language_selector.setCurrentText("简体中文")
    window.settings_dialog.concurrency_spin.setValue(4)
    window.settings_dialog.per_server_concurrency_spin.setValue(2)
    window.settings_dialog.limit_spin.setValue(256)
    window.settings_dialog.apply_button.click()

    assert window.current_theme == "dark"
    assert window.current_language == "zh_CN"
    assert window.transfer_settings.max_concurrent == 4
    assert window.transfer_settings.max_concurrent_per_server == 2
    assert window.transfer_settings.bytes_per_second_limit == 256 * 1024


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
    assert not window.local_panel.table.showGrid()
    assert window.local_panel.table.itemDelegate().uses_full_row_activity
    assert window.local_panel.table.itemDelegate().clears_cell_selection_paint
    assert window.local_panel.table.full_row_hover_color == hover_color_for_theme(window.current_theme)
    window.local_panel.table.set_hovered_row(1)
    assert window.local_panel.table.hovered_row == 1

    window.local_panel.table.setCurrentCell(1, 2)

    assert window.local_panel.selected_name() == "src"
    assert window.local_panel.selected_is_dir() is True
    assert window.local_panel.table.item(1, 2).data(Qt.ItemDataRole.UserRole) is True


def test_file_panels_use_resizable_columns_without_content_width_scans(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)

    header = window.local_panel.table.horizontalHeader()

    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Interactive
    assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.Interactive
    assert header.sectionResizeMode(2) == QHeaderView.ResizeMode.Interactive
    assert header.stretchLastSection()


def test_file_panel_shows_icons_for_parent_directories_and_file_suffixes(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)
    window.local_panel.set_entries(
        [
            type(
                "Entry",
                (),
                {"name": "src", "is_dir": True, "size_bytes": 0, "modified_time": None},
            )(),
            type(
                "Entry",
                (),
                {"name": "app.py", "is_dir": False, "size_bytes": 12, "modified_time": None},
            )(),
            type(
                "Entry",
                (),
                {"name": "package.zip", "is_dir": False, "size_bytes": 24, "modified_time": None},
            )(),
        ]
    )

    assert not window.local_panel.table.item(0, 0).icon().isNull()
    assert not window.local_panel.table.item(1, 0).icon().isNull()
    assert not window.local_panel.table.item(2, 0).icon().isNull()
    assert not window.local_panel.table.item(3, 0).icon().isNull()
    assert window.local_panel.table.iconSize().width() >= 22
    assert window.local_panel.table.iconSize().height() >= 22
    for row in range(window.local_panel.table.rowCount()):
        for column in range(1, window.local_panel.table.columnCount()):
            assert window.local_panel.table.item(row, column).icon().isNull()


def test_file_list_uses_extension_icons(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)
    window.local_panel.set_entries(
        [
            type("Entry", (), {"name": "src", "is_dir": True, "size_bytes": 0, "modified_time": None})(),
            type("Entry", (), {"name": "main.py", "is_dir": False, "size_bytes": 1, "modified_time": None})(),
            type("Entry", (), {"name": "readme.txt", "is_dir": False, "size_bytes": 1, "modified_time": None})(),
            type("Entry", (), {"name": "build.zip", "is_dir": False, "size_bytes": 1, "modified_time": None})(),
            type("Entry", (), {"name": "photo.png", "is_dir": False, "size_bytes": 1, "modified_time": None})(),
            type("Entry", (), {"name": "config.yaml", "is_dir": False, "size_bytes": 1, "modified_time": None})(),
            type("Entry", (), {"name": "blob.bin", "is_dir": False, "size_bytes": 1, "modified_time": None})(),
        ]
    )

    icon_keys = [
        window.local_panel.table.item(row, 0).data(ICON_KEY_ROLE)
        for row in range(window.local_panel.table.rowCount())
    ]

    assert icon_keys == [
        "parent-dir",
        "dir",
        "file-code-py",
        "file-text",
        "file-archive",
        "file-image",
        "file-config",
        "file-unknown",
    ]


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


def test_file_panel_keyboard_shortcuts(qtbot, tmp_path) -> None:
    controller = FakeController()
    window = MainWindow(
        controller=controller,
        delete_confirmer=lambda _parent, _names, _remote: True,
    )
    qtbot.addWidget(window)
    local_root = tmp_path / "local"
    local_root.mkdir()
    window.local_panel.path_edit.setText(str(local_root))
    window.local_panel.set_entries(
        [
            type("Entry", (), {"name": "src", "is_dir": True, "size_bytes": 0, "modified_time": None})(),
            type("Entry", (), {"name": "a.txt", "is_dir": False, "size_bytes": 1, "modified_time": None})(),
        ]
    )
    window.local_panel.table.setFocus()

    qtbot.keyClick(window.local_panel.table, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert window.local_panel.selected_names() == ["src", "a.txt"]

    qtbot.keyClick(window.local_panel.table, Qt.Key.Key_F5)
    assert controller.local_refreshes[-1] == local_root

    window.local_panel.clear_selection()
    window.local_panel.table.selectRow(1)
    qtbot.keyClick(window.local_panel.table, Qt.Key.Key_Return)
    assert controller.local_refreshes[-1] == local_root / "src"

    window.local_panel.path_edit.setText(str(local_root / "src"))
    qtbot.keyClick(window.local_panel.table, Qt.Key.Key_Backspace)
    assert controller.local_refreshes[-1] == local_root


def test_delete_requires_confirmation(qtbot, tmp_path) -> None:
    decisions = [False, True]
    controller = FakeController()
    window = MainWindow(
        controller=controller,
        delete_confirmer=lambda _parent, _names, _remote: decisions.pop(0),
    )
    qtbot.addWidget(window)
    local_root = tmp_path / "local"
    local_root.mkdir()
    window.local_panel.path_edit.setText(str(local_root))
    window.local_panel.set_entries(
        [
            type("Entry", (), {"name": "a.txt", "is_dir": False, "size_bytes": 1, "modified_time": None})(),
        ]
    )
    window.local_panel.table.selectRow(1)

    window._handle_local_delete_action()
    assert controller.deleted == []

    window._handle_local_delete_action()
    assert controller.deleted == [(local_root / "a.txt", False, False)]


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
    _use_english(window)

    menus = {action.text(): action.menu() for action in window.menuBar().actions()}
    assert "Help" in menus
    help_actions = {action.text(): action for action in window.help_menu.actions()}

    assert set(help_actions) == {
        "Getting Started",
        "About FileZall",
        "Version",
        "Protocols",
        "Commercial",
    }
    assert help_actions["Getting Started"].statusTip()
    assert help_actions["About FileZall"].statusTip()
    assert help_actions["Version"].statusTip()
    assert help_actions["Protocols"].statusTip()
    assert help_actions["Commercial"].statusTip()


def test_getting_started_guide_opens_from_help_menu(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)
    _use_english(window)
    window.show()
    qtbot.waitExposed(window)

    window.getting_started_action.trigger()

    dialog = window.getting_started_dialog
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "Getting Started"
    assert [label.text() for label in dialog.step_labels] == [
        "1. Create or choose a connection.",
        "2. Enter server credentials.",
        "3. Connect and load the remote home directory.",
        "4. Install or update the Agent when monitoring is needed.",
        "5. Choose local and remote folders.",
        "6. Upload, download, or add selected files to the queue.",
    ]

    qtbot.mouseClick(dialog.focus_connection_button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: window.connection_bar.host_edit.hasFocus(), timeout=1000)


def test_getting_started_guide_follows_language(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)

    window.chinese_language_action.trigger()
    assert window.getting_started_action.text() == "入门向导"
    assert window.getting_started_action.statusTip() == "显示首次使用向导"

    window.getting_started_action.trigger()
    dialog = window.getting_started_dialog
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "入门向导"
    assert dialog.focus_connection_button.text() == "定位到连接"

    window.english_language_action.trigger()
    assert window.getting_started_action.text() == "Getting Started"
    assert window.getting_started_action.statusTip() == "Show the first-use guide"
    assert dialog.windowTitle() == "Getting Started"
    assert dialog.focus_connection_button.text() == "Focus Connection"


def test_first_run_guide_opens_when_not_dismissed(qtbot) -> None:
    settings = FakeSettings(dismissed=False)
    window = MainWindow(controller=FakeController(), onboarding_settings=settings)
    qtbot.addWidget(window)
    _use_english(window)

    qtbot.waitUntil(
        lambda: window.getting_started_dialog is not None
        and window.getting_started_dialog.isVisible(),
        timeout=1000,
    )

    dialog = window.getting_started_dialog
    qtbot.addWidget(dialog)
    assert dialog.dismiss_checkbox.text() == "Do not show again"

    dialog.dismiss_checkbox.setChecked(True)

    assert settings.saved[-1] == ("onboarding.dismissed", True)


def test_first_run_guide_stays_closed_after_dismissal(qtbot) -> None:
    window = MainWindow(
        controller=FakeController(),
        onboarding_settings=FakeSettings(dismissed=True),
    )
    qtbot.addWidget(window)

    qtbot.wait(50)

    assert window.getting_started_dialog is None


def test_getting_started_test_connection_shows_clear_failure(qtbot) -> None:
    controller = AuthenticationFailingConnectController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    _use_english(window)
    window.connection_bar.host_edit.setText("example.com")
    window.connection_bar.port_edit.setText("2222")
    window.connection_bar.username_edit.setText("deploy")
    window.connection_bar.secret_edit.setText("secret")

    window.getting_started_action.trigger()
    dialog = window.getting_started_dialog
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.test_connection_button, Qt.MouseButton.LeftButton)

    site, password, remember_secret = controller.connect_calls[0]
    assert site.host == "example.com"
    assert site.port == 2222
    assert password == "secret"
    assert remember_secret is False
    expected = "Authentication failed. Check the username, password, SSH key, or passphrase."
    assert dialog.status_label.text() == expected
    assert f"Connection test failed: {expected}" in window.log_view.toPlainText()


def test_getting_started_saves_successful_site(qtbot) -> None:
    controller = FakeController()
    settings = FakeSettings()
    window = MainWindow(controller=controller, onboarding_settings=settings)
    qtbot.addWidget(window)
    _use_english(window)
    window.connection_bar.host_edit.setText("example.com")
    window.connection_bar.port_edit.setText("2222")
    window.connection_bar.username_edit.setText("deploy")
    window.connection_bar.secret_edit.setText("secret")
    window.remote_panel.path_edit.setText("/var/www")

    window.getting_started_action.trigger()
    dialog = window.getting_started_dialog
    qtbot.addWidget(dialog)

    assert dialog.save_site_button.isEnabled() is False

    qtbot.mouseClick(dialog.test_connection_button, Qt.MouseButton.LeftButton)

    assert dialog.status_label.text() == "Connection test passed."
    assert dialog.save_site_button.isEnabled() is True
    controller.loaded_sites = False

    qtbot.mouseClick(dialog.save_site_button, Qt.MouseButton.LeftButton)

    site, password, remember_secret = controller.connect_calls[-1]
    assert site.host == "example.com"
    assert str(site.default_remote_path) == "/var/www"
    assert password == "secret"
    assert remember_secret is True
    assert controller.loaded_sites is True
    assert settings.dismissed is True


def test_main_window_has_session_menu_new_session_action(qtbot) -> None:
    opened = []

    class DummySessionWindow:
        def show(self) -> None:
            opened.append("shown")

    window = MainWindow(
        controller=FakeController(),
        new_session_factory=lambda: DummySessionWindow(),
    )
    qtbot.addWidget(window)
    _use_english(window)

    menus = {action.text(): action.menu() for action in window.menuBar().actions()}
    assert "Session" in menus
    session_actions = {action.text(): action for action in window.session_menu.actions()}

    session_actions["New Session"].trigger()

    assert opened == ["shown"]
    assert window._session_windows


def test_main_window_opens_site_manager(qtbot) -> None:
    repository = FakeSiteRepository(
        [
            SiteProfile(
                id="prod",
                name="Production",
                host="example.com",
                port=22,
                protocol=Protocol.SFTP,
                username="deploy",
                auth_mode=AuthMode.PASSWORD,
            )
        ]
    )
    controller = FakeController()
    window = MainWindow(controller=controller, site_repository=repository)
    qtbot.addWidget(window)
    _use_english(window)

    window.site_manager_action.trigger()

    dialog = window.site_manager_dialog
    qtbot.addWidget(dialog)
    assert dialog.isVisible()
    assert dialog.table.rowCount() == 1

    dialog.sites_changed.emit()

    assert controller.loaded_sites is True


def test_main_window_has_theme_menu_actions(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)
    _use_english(window)

    menus = {action.text(): action.menu() for action in window.menuBar().actions()}
    assert "Settings" in menus
    assert window.theme_menu in [action.menu() for action in window.settings_menu.actions()]
    theme_actions = {
        action.text(): action
        for action in window.theme_menu.actions()
        if not action.isSeparator()
    }

    assert set(theme_actions) == {"System", "Light", "Dark", "Compact", "Standard", "Comfortable"}
    assert window.system_theme_action.isCheckable()
    assert window.light_theme_action.isCheckable()
    assert window.dark_theme_action.isCheckable()
    assert window.compact_density_action.isCheckable()
    assert window.standard_density_action.isCheckable()
    assert window.comfortable_density_action.isCheckable()
    assert window.system_theme_action.isChecked()


def test_main_window_applies_theme_actions(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)

    window.dark_theme_action.trigger()
    dark_stylesheet = window.styleSheet()

    assert window.current_theme == "dark"
    assert window.dark_theme_action.isChecked()
    assert "background-color: #111827" in dark_stylesheet

    window.light_theme_action.trigger()

    assert window.current_theme == "light"
    assert window.light_theme_action.isChecked()
    assert window.styleSheet() != dark_stylesheet
    assert "background-color: #f5f7fb" in window.styleSheet()


def test_file_list_density_actions_update_row_height(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)

    assert window.file_list_density == "standard"
    assert window.local_panel.table.verticalHeader().defaultSectionSize() == 30
    assert window.remote_panel.table.verticalHeader().defaultSectionSize() == 30

    window.compact_density_action.trigger()
    assert window.file_list_density == "compact"
    assert window.local_panel.table.verticalHeader().defaultSectionSize() == 24
    assert window.remote_panel.table.verticalHeader().defaultSectionSize() == 24

    window.local_panel.set_entries(
        [
            type("Entry", (), {"name": "a.txt", "is_dir": False, "size_bytes": 1, "modified_time": None})(),
        ]
    )
    assert window.local_panel.table.verticalHeader().defaultSectionSize() == 24

    window.comfortable_density_action.trigger()
    assert window.file_list_density == "comfortable"
    assert window.local_panel.table.verticalHeader().defaultSectionSize() == 36
    assert window.remote_panel.table.verticalHeader().defaultSectionSize() == 36


def test_main_window_has_language_menu_actions(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)

    menus = {action.text(): action.menu() for action in window.menuBar().actions()}
    assert "设置" in menus
    assert window.language_menu in [action.menu() for action in window.settings_menu.actions()]
    language_actions = {action.text(): action for action in window.language_menu.actions()}

    assert set(language_actions) == {"System", "English", "简体中文"}
    assert window.system_language_action.isCheckable()
    assert window.english_language_action.isCheckable()
    assert window.chinese_language_action.isCheckable()
    assert window.system_language_action.isChecked()


def test_main_window_applies_language_actions(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)

    window.chinese_language_action.trigger()

    assert window.current_language == "zh_CN"
    assert window.local_panel.title.text() == "本地文件"
    assert window.remote_panel.title.text() == "远端文件"
    assert window.local_panel.refresh_button.text() == "刷新"
    assert window.local_panel.action_button.text() == "上传"
    assert window.remote_panel.action_button.text() == "下载"
    assert window.local_panel.table.horizontalHeaderItem(0).text() == "名称"
    assert window.local_panel.transfer_action.text() == "上传"
    assert window.remote_panel.transfer_action.text() == "下载"

    window.english_language_action.trigger()

    assert window.current_language == "en"
    assert window.local_panel.title.text() == "Local Files"
    assert window.local_panel.refresh_button.text() == "Refresh"
    assert window.local_panel.table.horizontalHeaderItem(0).text() == "Name"


def test_translation_keys_are_complete(qtbot) -> None:
    assert set(_TRANSLATIONS[EN_LANGUAGE]) == set(_TRANSLATIONS[ZH_CN_LANGUAGE])
    required_keys = [
        "density.compact",
        "density.standard",
        "density.comfortable",
        "logs.copy_error",
        "resource.range",
        "resource.disk_selector",
        "resource.sort",
        "resource.all_disks",
        "resource.process_filter",
        "confirm.delete_title",
        "confirm.delete_message",
    ]
    for key in required_keys:
        assert t(EN_LANGUAGE, key) != key
        assert t(ZH_CN_LANGUAGE, key) != key

    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)
    window.chinese_language_action.trigger()

    assert window.compact_density_action.text() == "紧凑"
    assert window.standard_density_action.text() == "标准"
    assert window.comfortable_density_action.text() == "舒适"
    assert window.log_viewer.copy_error_button.text() == "复制错误"
    assert window.resource_range_label.text() == "范围"
    assert window.resource_sort_label.text() == "排序"
    assert window.process_filter_edit.placeholderText() == "筛选进程"


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


def test_main_window_redacts_sensitive_values_from_logs_and_export(qtbot, tmp_path) -> None:
    export_path = tmp_path / "filezall.log"
    window = MainWindow(
        controller=FakeController(),
        log_file_chooser=lambda _parent: str(export_path),
    )
    qtbot.addWidget(window)

    window.append_log("Connected password=secret token=abc Authorization: Bearer raw-token")
    window.export_logs_action.trigger()

    visible_logs = window.log_view.toPlainText()
    exported_logs = export_path.read_text(encoding="utf-8")
    assert "secret" not in visible_logs
    assert "raw-token" not in visible_logs
    assert "password=<redacted>" in visible_logs
    assert "token=<redacted>" in exported_logs
    assert "Authorization: Bearer <redacted>" in exported_logs


def test_main_window_filters_log_categories(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)

    window.append_log("Connected to Production")
    window.append_log("Agent install confirmed")
    window.append_log("Resource snapshot refreshed")
    window.append_log("Connection failed: bad password")

    window.log_viewer.set_category_filter("agent")
    assert "Agent install confirmed" in window.log_view.toPlainText()
    assert "Connected to Production" not in window.log_view.toPlainText()

    window.log_viewer.set_category_filter("error")
    assert "Connection failed: bad password" in window.log_view.toPlainText()
    assert "Resource snapshot refreshed" not in window.log_view.toPlainText()

    window.log_viewer.set_category_filter("all")
    assert "Connected to Production" in window.log_view.toPlainText()
    assert "Resource snapshot refreshed" in window.log_view.toPlainText()


def test_main_window_exports_diagnostic_package(qtbot, tmp_path) -> None:
    diagnostic_path = tmp_path / "diagnostics.zip"
    logs_dir = tmp_path / "runtime-logs"
    logs_dir.mkdir()
    (logs_dir / "filezall-runtime.log").write_text("runtime trace\n", encoding="utf-8")
    window = MainWindow(
        controller=FakeController(),
        diagnostic_file_chooser=lambda _parent: str(diagnostic_path),
        diagnostics_logs_dir=logs_dir,
    )
    qtbot.addWidget(window)

    window.append_log("Uploaded app.txt")
    window.export_diagnostics_action.trigger()

    with zipfile.ZipFile(diagnostic_path) as archive:
        assert "Uploaded app.txt" in archive.read("logs/session.log").decode("utf-8")
        assert "runtime trace" in archive.read("logs/filezall-runtime.log").decode("utf-8")


def test_main_window_diagnostic_package_includes_ui_state_snapshot(qtbot, tmp_path) -> None:
    diagnostic_path = tmp_path / "diagnostics.zip"
    window = MainWindow(
        controller=FakeController(),
        diagnostic_file_chooser=lambda _parent: str(diagnostic_path),
    )
    qtbot.addWidget(window)
    window.transfer_status_clock = lambda: datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
    window._resource_refresh_running = True
    window.append_log("Background operation failed [resource refresh]: timeout", category="error", level="error")
    window.set_transfer_items(
        [
            TransferItem(
                id="item-1",
                task_id="task-1",
                server_id="site-1",
                direction=Direction.UPLOAD,
                source_path=tmp_path / "app.txt",
                destination_path=PurePosixPath("/srv/app.txt"),
                temporary_path=PurePosixPath("/srv/.filezall.app.txt.part"),
                size_bytes=100,
                protocol=Protocol.SFTP,
                bytes_transferred=25,
                status=TransferStatus.RUNNING,
            ),
            TransferItem(
                id="item-2",
                task_id="task-2",
                server_id="site-1",
                direction=Direction.DOWNLOAD,
                source_path=PurePosixPath("/srv/error.txt"),
                destination_path=tmp_path / "error.txt",
                temporary_path=tmp_path / ".filezall.error.txt.part",
                size_bytes=100,
                protocol=Protocol.SFTP,
                status=TransferStatus.FAILED,
                failure_reason="network timeout",
            ),
            TransferItem(
                id="item-3",
                task_id="task-3",
                server_id="site-2",
                direction=Direction.UPLOAD,
                source_path=tmp_path / "retry.txt",
                destination_path=PurePosixPath("/srv/retry.txt"),
                temporary_path=PurePosixPath("/srv/.filezall.retry.txt.part"),
                size_bytes=100,
                protocol=Protocol.SFTP,
                status=TransferStatus.RETRYING,
                retry_count=2,
                failure_reason="temporary network down",
                next_retry_at=datetime(2026, 6, 27, 12, 0, 30, tzinfo=UTC),
            ),
        ]
    )

    window.export_diagnostics_action.trigger()

    with zipfile.ZipFile(diagnostic_path) as archive:
        state = json.loads(archive.read("state/snapshot.json").decode("utf-8"))

    assert state["resource_refresh"]["running"] is True
    assert state["transfer_queue"]["total"] == 3
    assert state["transfer_queue"]["by_status"] == {"failed": 1, "retrying": 1, "running": 1}
    assert state["transfer_queue"]["retrying"]["total"] == 1
    assert state["transfer_queue"]["retrying"]["waiting"] == 1
    assert state["transfer_queue"]["retrying"]["next_retry_at"] == "2026-06-27T12:00:30+00:00"
    assert state["transfer_queue"]["failures"]["recent"] == [
        {
            "item_id": "item-2",
            "task_id": "task-2",
            "server_id": "site-1",
            "status": "failed",
            "retry_count": 0,
            "reason": "network timeout",
        },
        {
            "item_id": "item-3",
            "task_id": "task-3",
            "server_id": "site-2",
            "status": "retrying",
            "retry_count": 2,
            "reason": "temporary network down",
        },
    ]
    assert state["logs"]["error_count"] == 1
    assert state["logs"]["recent_errors"][0]["message"] == "Background operation failed [resource refresh]: timeout"


def test_main_window_displays_agent_version_when_available(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)

    window.set_agent_status(True, version="0.1.0")

    assert window.agent_status_label.text() == "Agent installed v0.1.0"


def test_main_window_marks_outdated_agent_as_update_available(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)

    window.set_agent_status(True, version="0.0.9")

    assert window.agent_status_label.text() == "Agent update available v0.0.9 -> v0.1.0"
    assert not window.resource_install_agent_button.isHidden()
    assert not window.resource_uninstall_agent_button.isHidden()


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


def test_remote_directory_navigation_shows_loading_state_while_request_runs(qtbot) -> None:
    controller = ObservingRemoteLoadingController()
    window = MainWindow(controller=controller)
    controller.window = window
    qtbot.addWidget(window)
    _use_english(window)
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

    window.remote_panel.table.cellDoubleClicked.emit(1, 0)

    assert controller.loading_snapshot == (
        False,
        False,
        "Loading remote directory /home/deploy/releases...",
    )
    assert window.remote_panel.table.isEnabled()
    assert window.remote_panel.refresh_button.isEnabled()


def test_remote_directory_navigation_runs_in_background(qtbot) -> None:
    controller = SlowRemoteDataController(delay_seconds=0.3)
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
                modified_time=None,
            )
        ]
    )

    started_at = time.perf_counter()
    window.remote_panel.table.cellDoubleClicked.emit(1, 0)
    elapsed = time.perf_counter() - started_at

    assert elapsed < 0.2
    assert not window.remote_panel.table.isEnabled()
    qtbot.waitUntil(lambda: window.remote_panel.name_at(1) == "nested", timeout=3000)
    assert window.remote_panel.path_edit.text() == "/home/deploy/releases"
    assert window.remote_panel.table.isEnabled()


def test_remote_directory_navigation_updates_widgets_on_main_thread(qtbot) -> None:
    controller = SlowRemoteDataController(delay_seconds=0.01)
    window = ThreadRecordingWindow(controller=controller)
    qtbot.addWidget(window)

    window._load_remote_directory(PurePosixPath("/home/deploy/releases"))

    qtbot.waitUntil(lambda: bool(window.remote_entries_threads), timeout=3000)
    assert window.remote_entries_threads == [window.thread()]


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


def test_main_window_path_history_selects_previous_directories(qtbot, tmp_path) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    local_one = tmp_path / "one"
    local_two = tmp_path / "two"
    local_one.mkdir()
    local_two.mkdir()

    window.local_panel.path_edit.setText(str(local_one))
    qtbot.keyClick(window.local_panel.path_edit, Qt.Key.Key_Return)
    window.local_panel.path_edit.setText(str(local_two))
    qtbot.keyClick(window.local_panel.path_edit, Qt.Key.Key_Return)
    window.remote_panel.path_edit.setText("/srv/app")
    qtbot.keyClick(window.remote_panel.path_edit, Qt.Key.Key_Return)
    window.remote_panel.path_edit.setText("/srv/logs")
    qtbot.keyClick(window.remote_panel.path_edit, Qt.Key.Key_Return)

    window.local_panel.path_edit.setCurrentIndex(
        window.local_panel.path_edit.findText(str(local_one))
    )
    window.local_panel.path_edit.activated.emit(window.local_panel.path_edit.currentIndex())
    window.remote_panel.path_edit.setCurrentIndex(
        window.remote_panel.path_edit.findText("/srv/app")
    )
    window.remote_panel.path_edit.activated.emit(window.remote_panel.path_edit.currentIndex())

    assert [window.local_panel.path_edit.itemText(index) for index in range(2)] == [
        str(local_one),
        str(local_two),
    ]
    assert [window.remote_panel.path_edit.itemText(index) for index in range(2)] == [
        "/srv/app",
        "/srv/logs",
    ]
    assert controller.local_refreshes[-1] == local_one
    assert str(controller.remote_refreshes[-1]) == "/srv/app"


def test_file_panel_context_actions_route_to_controller(qtbot, tmp_path) -> None:
    controller = FakeController()
    window = MainWindow(
        controller=controller,
        delete_confirmer=lambda _parent, _names, _remote: True,
    )
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
    assert controller.deleted[0] == (local_root / "app.txt", False, False)
    assert controller.created_dirs[0] == (local_root, False)
    assert controller.created_files[0] == (local_root, False)
    assert controller.queued[1] == (PurePosixPath("/home/deploy/remote.txt"), local_root / "remote.txt", Direction.DOWNLOAD)
    assert controller.deleted[1] == (PurePosixPath("/home/deploy/remote.txt"), True, False)


def test_file_panel_delete_actions_pass_directory_state(qtbot, tmp_path) -> None:
    controller = FakeController()
    window = MainWindow(
        controller=controller,
        delete_confirmer=lambda _parent, _names, _remote: True,
    )
    qtbot.addWidget(window)
    local_root = tmp_path / "local"
    local_root.mkdir()
    window.local_panel.path_edit.setText(str(local_root))
    window.remote_panel.path_edit.setText("/home/deploy")
    window.local_panel.set_entries(
        [
            RemoteFileEntry(
                path=PurePosixPath("local-dir"),
                name="local-dir",
                is_dir=True,
                size_bytes=0,
                modified_time=None,
            )
        ]
    )
    window.remote_panel.set_entries(
        [
            RemoteFileEntry(
                path=PurePosixPath("/home/deploy/logs"),
                name="logs",
                is_dir=True,
                size_bytes=0,
                modified_time=None,
            )
        ]
    )
    window.local_panel.table.selectRow(1)
    window.remote_panel.table.selectRow(1)

    window.local_panel.delete_action.trigger()
    window.remote_panel.delete_action.trigger()

    assert controller.deleted == [
        (local_root / "local-dir", False, True),
        (PurePosixPath("/home/deploy/logs"), True, True),
    ]


def test_file_panel_rename_actions_route_to_controller(qtbot, tmp_path) -> None:
    controller = FakeController()
    window = MainWindow(
        controller=controller,
        rename_prompt=lambda _parent, _old_name: "renamed.txt",
    )
    qtbot.addWidget(window)
    local_root = tmp_path / "local"
    local_root.mkdir()
    window.local_panel.path_edit.setText(str(local_root))
    window.remote_panel.path_edit.setText("/home/deploy")
    window.local_panel.set_placeholder_row("app.txt")
    window.remote_panel.set_placeholder_row("remote.txt")
    window.local_panel.table.selectRow(0)
    window.remote_panel.table.selectRow(0)

    window.local_panel.rename_action.trigger()
    window.remote_panel.rename_action.trigger()

    assert controller.renamed == [
        (local_root / "app.txt", local_root / "renamed.txt", False),
        (PurePosixPath("/home/deploy/remote.txt"), PurePosixPath("/home/deploy/renamed.txt"), True),
    ]


def test_file_panel_copy_path_actions_write_clipboard(qtbot, tmp_path) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)
    local_root = tmp_path / "local"
    local_root.mkdir()
    window.local_panel.path_edit.setText(str(local_root))
    window.remote_panel.path_edit.setText("/home/deploy")
    window.local_panel.set_placeholder_row("app.txt")
    window.remote_panel.set_placeholder_row("remote.txt")
    window.local_panel.table.selectRow(0)
    window.remote_panel.table.selectRow(0)

    window.local_panel.copy_path_action.trigger()
    expected_local = str(local_root / "app.txt")
    assert QApplication.clipboard().text() == expected_local or window.last_copied_text == expected_local

    window.remote_panel.copy_path_action.trigger()
    assert QApplication.clipboard().text() == "/home/deploy/remote.txt" or window.last_copied_text == "/home/deploy/remote.txt"


def test_main_window_refresh_buttons_clear_current_selection(qtbot, tmp_path) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    window.local_panel.path_edit.setText(str(tmp_path))
    window.local_panel.set_placeholder_row("app.txt")
    window.local_panel.table.selectRow(0)

    qtbot.mouseClick(window.local_panel.refresh_button, Qt.MouseButton.LeftButton)

    assert window.local_panel.table.selectionModel().selectedRows() == []
    assert window.local_panel.table.currentRow() == -1


def test_file_panel_set_entries_clears_current_and_hover_rows(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)
    window.local_panel.set_entries(
        [
            type("Entry", (), {"name": "one", "is_dir": True, "size_bytes": 0, "modified_time": None})(),
            type("Entry", (), {"name": "two", "is_dir": True, "size_bytes": 0, "modified_time": None})(),
            type("Entry", (), {"name": "three", "is_dir": True, "size_bytes": 0, "modified_time": None})(),
        ]
    )
    window.local_panel.table.selectRow(3)
    window.local_panel.table.setCurrentCell(3, 0)
    window.local_panel.table.set_hovered_row(3)

    window.local_panel.set_entries(
        [
            type("Entry", (), {"name": "nine", "is_dir": True, "size_bytes": 0, "modified_time": None})(),
            type("Entry", (), {"name": "six", "is_dir": True, "size_bytes": 0, "modified_time": None})(),
            type("Entry", (), {"name": "seven", "is_dir": True, "size_bytes": 0, "modified_time": None})(),
            type("Entry", (), {"name": "five", "is_dir": True, "size_bytes": 0, "modified_time": None})(),
        ]
    )

    assert window.local_panel.table.selectionModel().selectedRows() == []
    assert window.local_panel.table.currentRow() == -1
    assert window.local_panel.table.hovered_row == -1


def test_file_panel_virtualizes_large_directory_rendering(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)
    entries = [
        type(
            "Entry",
            (),
            {
                "name": f"file-{index}.txt",
                "is_dir": False,
                "size_bytes": index,
                "modified_time": None,
            },
        )()
        for index in range(750)
    ]

    window.local_panel.set_entries(entries)

    assert window.local_panel.is_loading_entries is False
    assert window.local_panel.table.rowCount() == len(entries) + 1
    assert window.local_panel.entry_model.rowCount() == len(entries) + 1
    assert window.local_panel.load_progress_label.text() == "750 items"


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
    assert window.connection_state_label.property("connectionState") == "connected"
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
    assert window.connection_state_label.property("connectionState") == "failed"
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
    assert window.connection_state_label.property("connectionState") == "connecting"
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


def test_heartbeat_check_blinks_status_light_at_detection_frequency(qtbot) -> None:
    controller = FakeController()
    controller.heartbeat_results = [True]
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)

    window._handle_heartbeat_tick()

    assert window.connection_state_label.property("lastBlinkColor") == "goldenrod"
    assert window.connection_state_label.property("blinkCount") == 1


def test_disconnect_button_calls_controller_logs_and_stops_heartbeat(qtbot) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    window.heartbeat_timer.start()
    window.resource_refresh_timer.start()
    window._set_connection_state("Connected", "green")

    qtbot.mouseClick(window.connection_bar.disconnect_button, Qt.MouseButton.LeftButton)

    assert controller.disconnect_calls == 1
    assert not window.heartbeat_timer.isActive()
    assert not window.resource_refresh_timer.isActive()
    assert window.connection_state_label.toolTip() == "Disconnected"
    assert "grey" in window.connection_state_label.styleSheet()
    logs = window.log_view.toPlainText()
    assert "Disconnect requested" in logs
    assert "Disconnected" in logs


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


def test_background_worker_failures_get_diagnostic_log_context(qtbot) -> None:
    window = MainWindow(controller=FailingSnapshotController())
    qtbot.addWidget(window)

    window._handle_resource_refresh_tick()

    qtbot.waitUntil(
        lambda: "Background operation failed [resource refresh]: agent timeout"
        in window.log_view.toPlainText(),
        timeout=3000,
    )
    assert "Resource refresh failed: agent timeout" in window.log_view.toPlainText()


def test_resource_refresh_timer_starts_after_successful_connect(qtbot) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    window.connection_bar.host_edit.setText("example.com")
    window.connection_bar.username_edit.setText("deploy")
    window.connection_bar.secret_edit.setText("secret")

    qtbot.mouseClick(window.connection_bar.connect_button, Qt.MouseButton.LeftButton)

    assert window.resource_refresh_timer.isActive()


def test_async_connect_updates_remote_widgets_on_main_thread(qtbot) -> None:
    controller = AsyncConnectController()
    window = ThreadRecordingWindow(controller=controller)
    qtbot.addWidget(window)
    window.connection_bar.host_edit.setText("example.com")
    window.connection_bar.username_edit.setText("deploy")
    window.connection_bar.secret_edit.setText("secret")

    qtbot.mouseClick(window.connection_bar.connect_button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: bool(window.remote_entries_threads), timeout=3000)
    assert window.remote_entries_threads == [window.thread()]
    assert controller.connect_calls
    assert window.connection_state_label.toolTip() == "Connected"


def test_successful_connect_triggers_immediate_resource_refresh(qtbot) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    window.connection_bar.host_edit.setText("example.com")
    window.connection_bar.username_edit.setText("deploy")
    window.connection_bar.secret_edit.setText("secret")

    qtbot.mouseClick(window.connection_bar.connect_button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: controller.resource_refreshes == 1, timeout=3000)


def test_resource_refresh_tick_runs_controller_refresh_in_background(qtbot) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)

    window._handle_resource_refresh_tick()

    qtbot.waitUntil(lambda: controller.resource_refreshes == 1, timeout=3000)
    assert window._resource_refresh_running is False


def test_resource_refresh_updates_widgets_on_main_thread(qtbot) -> None:
    controller = SnapshotController()
    window = ThreadRecordingWindow(controller=controller)
    qtbot.addWidget(window)

    window._handle_resource_refresh_tick()

    qtbot.waitUntil(lambda: bool(window.resource_snapshot_threads), timeout=3000)
    assert window.resource_snapshot_threads == [window.thread()]


def test_resource_refresh_success_is_written_to_logs(qtbot) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)

    window._handle_resource_refresh_tick()

    qtbot.waitUntil(
        lambda: "Resource snapshot refreshed" in window.log_view.toPlainText(),
        timeout=3000,
    )


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


def test_main_window_displays_detected_agent_status(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)
    window.set_monitoring_status("Resource monitoring requires SSH or FileZall Agent.")

    window.set_agent_status(None)
    assert window.agent_status_label.text() == "Checking Agent..."
    assert not window.resource_install_agent_button.isHidden()
    assert window.resource_uninstall_agent_button.isHidden()

    window.set_agent_status(True)
    assert window.agent_status_label.text() == "Agent installed"
    assert window.resource_install_agent_button.isHidden()
    assert not window.resource_uninstall_agent_button.isHidden()


def test_main_window_updates_agent_status_card(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)

    window.set_agent_status_model(
        AgentStatusViewModel(
            state=AgentStatus.OUTDATED,
            version="0.0.1",
            message="Agent update is available.",
            primary_action="Update Agent",
            danger_action="Uninstall Agent",
        )
    )

    assert window.agent_status_card.state_label.text() == "Outdated"
    assert window.agent_status_card.version_label.text() == "v0.0.1"
    assert window.agent_status_card.primary_button.text() == "Update Agent"
    assert window.agent_status_card.primary_button.property("buttonRole") == "warning"
    assert window.agent_status_card.danger_button.text() == "Uninstall Agent"


def test_resource_agent_install_button_uses_confirmed_install_flow(qtbot) -> None:
    controller = FakeController()
    window = MainWindow(
        controller=controller,
        agent_install_confirmer=lambda _parent: True,
    )
    qtbot.addWidget(window)
    window.set_monitoring_status("Resource monitoring requires SSH or FileZall Agent.")

    qtbot.mouseClick(window.resource_install_agent_button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: controller.agent_installs == 1, timeout=3000)
    assert controller.agent_installs == 1


def test_resource_agent_uninstall_button_uses_confirmed_flow_and_logs(qtbot) -> None:
    controller = FakeController()
    window = MainWindow(
        controller=controller,
        agent_install_confirmer=lambda _parent: True,
    )
    qtbot.addWidget(window)
    window.set_monitoring_status("Resource monitoring requires SSH or FileZall Agent.")

    assert not window.resource_uninstall_agent_button.isHidden()

    qtbot.mouseClick(window.resource_uninstall_agent_button, Qt.MouseButton.LeftButton)

    qtbot.waitUntil(lambda: controller.agent_uninstalls == 1, timeout=3000)
    assert controller.agent_uninstalls == 1
    logs = window.log_view.toPlainText()
    assert "Agent uninstall requested" in logs
    assert "Agent uninstall confirmed" in logs
    assert "Agent uninstall command finished" in logs


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


def test_main_window_connects_saved_site_with_manual_secret_without_remembering(qtbot) -> None:
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
    window.connection_bar.secret_edit.setText("manual-secret")

    qtbot.mouseClick(window.connection_bar.connect_button, Qt.MouseButton.LeftButton)

    site, password, remember_secret = controller.connect_calls[0]
    assert site == saved_site
    assert password == "manual-secret"
    assert remember_secret is False


def test_saved_site_autofills_quick_connect_fields_without_reading_secret(qtbot, tmp_path) -> None:
    class SavedController(FakeController):
        def __init__(self) -> None:
            super().__init__()
            self.secret_lookup_count = 0

        def secret_for_site(self, site):
            self.secret_lookup_count += 1
            return "remembered-secret"

    controller = SavedController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    _use_english(window)
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
    assert window.connection_bar.secret_edit.text() == ""
    assert controller.secret_lookup_count == 0
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


def test_upload_prompts_for_conflict_policy(qtbot, tmp_path) -> None:
    decisions = []

    def choose_policy(_parent, destination_name: str):
        decisions.append(destination_name)
        return type(
            "Decision",
            (),
            {"policy": ConflictPolicy.RENAME, "apply_to_all": False},
        )()

    controller = FakeController()
    window = MainWindow(controller=controller, conflict_policy_prompt=choose_policy)
    qtbot.addWidget(window)
    local_root = tmp_path / "local"
    local_root.mkdir()
    (local_root / "app.txt").write_text("hello", encoding="utf-8")
    window.local_panel.path_edit.setText(str(local_root))
    window.remote_panel.path_edit.setText("/home/deploy")
    window.local_panel.set_entries(
        [
            type(
                "Entry",
                (),
                {"name": "app.txt", "is_dir": False, "size_bytes": 5, "modified_time": None},
            )(),
        ]
    )
    window.remote_panel.set_entries(
        [
            type(
                "Entry",
                (),
                {"name": "app.txt", "is_dir": False, "size_bytes": 2, "modified_time": None},
            )(),
        ]
    )

    window.local_panel.table.selectRow(1)
    qtbot.mouseClick(window.local_panel.action_button, Qt.MouseButton.LeftButton)

    assert decisions == ["app.txt"]
    assert controller.uploads == [(local_root / "app.txt", PurePosixPath("/home/deploy/app.txt"))]
    assert controller.upload_conflict_policies == [ConflictPolicy.RENAME]


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


def test_transfer_table_uses_model_view_for_large_queue_rendering(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)

    assert isinstance(window.transfer_table, QTableView)
    assert not isinstance(window.transfer_table, QTableWidget)
    assert window.transfer_table.model() is window.transfer_model


def test_direct_upload_and_download_show_immediate_transfer_progress_rows(qtbot, tmp_path) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    local_root = tmp_path / "local"
    local_root.mkdir()
    (local_root / "app.txt").write_text("hello", encoding="utf-8")
    window.local_panel.path_edit.setText(str(local_root))
    window.remote_panel.path_edit.setText("/home/deploy")
    window.local_panel.set_entries(
        [
            type(
                "Entry",
                (),
                {"name": "app.txt", "is_dir": False, "size_bytes": 5, "modified_time": None},
            )(),
        ]
    )
    window.remote_panel.set_entries(
        [
            type(
                "Entry",
                (),
                {"name": "remote.log", "is_dir": False, "size_bytes": 12, "modified_time": None},
            )(),
        ]
    )

    window.local_panel.table.selectRow(1)
    qtbot.mouseClick(window.local_panel.action_button, Qt.MouseButton.LeftButton)
    assert window.transfer_table.rowCount() == 1
    assert window.transfer_table.item(0, 1).text() == "upload"
    assert window.transfer_table.item(0, 2).text() == "app.txt"
    assert window.transfer_table.item(0, 3).text() == "0%"
    assert window.transfer_table.item(0, 8).text() == "Pending"

    window.remote_panel.table.selectRow(1)
    qtbot.mouseClick(window.remote_panel.action_button, Qt.MouseButton.LeftButton)
    assert window.transfer_table.rowCount() == 2
    assert window.transfer_table.item(1, 1).text() == "download"
    assert window.transfer_table.item(1, 2).text() == "remote.log"
    assert window.transfer_table.item(1, 3).text() == "0%"


def test_transfer_center_shows_directory_progress(qtbot, tmp_path) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)
    first = TransferItem(
        id="item-1",
        task_id="task-1",
        server_id="site-1",
        direction=Direction.UPLOAD,
        source_path=tmp_path / "site" / "assets" / "app.js",
        destination_path=PurePosixPath("/home/deploy/site/assets/app.js"),
        temporary_path=PurePosixPath("/home/deploy/site/assets/.filezall.app.js.part"),
        size_bytes=6,
        protocol=Protocol.SFTP,
        bytes_transferred=6,
        status=TransferStatus.COMPLETED,
    )
    second = TransferItem(
        id="item-2",
        task_id="task-1",
        server_id="site-1",
        direction=Direction.UPLOAD,
        source_path=tmp_path / "site" / "index.html",
        destination_path=PurePosixPath("/home/deploy/site/index.html"),
        temporary_path=PurePosixPath("/home/deploy/site/.filezall.index.html.part"),
        size_bytes=5,
        protocol=Protocol.SFTP,
        bytes_transferred=2,
        status=TransferStatus.RUNNING,
    )

    window.set_transfer_items([first, second])

    assert window.transfer_summary_label.text() == (
        "task-1: 2 files, 8 / 11 bytes, current index.html"
    )


def test_transfer_center_coalesces_running_progress_but_flushes_terminal_status(
    qtbot,
    tmp_path,
) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)

    def item(bytes_transferred: int, status: TransferStatus = TransferStatus.RUNNING):
        return TransferItem(
            id="item-1",
            task_id="task-1",
            server_id="site-1",
            direction=Direction.UPLOAD,
            source_path=tmp_path / "app.zip",
            destination_path=PurePosixPath("/home/deploy/app.zip"),
            temporary_path=PurePosixPath("/home/deploy/.filezall.app.zip.part"),
            size_bytes=100,
            protocol=Protocol.SFTP,
            bytes_transferred=bytes_transferred,
            status=status,
        )

    window.set_transfer_items([item(10)])
    assert window.transfer_table.item(0, 3).text() == "10%"

    window.set_transfer_items([item(20)])
    window.set_transfer_items([item(30)])

    assert window._optimistic_transfer_items[0].bytes_transferred == 30
    assert window.transfer_table.item(0, 3).text() == "10%"

    qtbot.waitUntil(
        lambda: window.transfer_table.item(0, 3).text() == "30%",
        timeout=1000,
    )

    window.set_transfer_items([item(100, TransferStatus.COMPLETED)])

    assert window.transfer_table.item(0, 3).text() == "100%"
    assert window.transfer_table.item(0, 8).text() == "Completed"


def test_transfer_center_shows_metrics_columns(qtbot, tmp_path) -> None:
    window = MainWindow(controller=FakeController())
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
        status=TransferStatus.FAILED,
        retry_count=2,
        bytes_per_second=2048,
        remaining_seconds=37,
        failure_reason="network down",
    )

    window.set_transfer_items([item])

    headers = [
        window.transfer_table.horizontalHeaderItem(index).text()
        for index in range(window.transfer_table.columnCount())
    ]
    assert headers == [
        "Server",
        "Direction",
        "File",
        "Progress",
        "Speed",
        "Remaining",
        "Retries",
        "Failure",
        "Status",
    ]
    assert window.transfer_table.item(0, 4).text() == "2.0 KB/s"
    assert window.transfer_table.item(0, 5).text() == "37s"
    assert window.transfer_table.item(0, 6).text() == "2"
    assert window.transfer_table.item(0, 7).text() == "network down"


def test_transfer_center_has_concurrency_and_limit_controls(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)
    _use_english(window)

    assert window.transfer_concurrency_label.text() == "Concurrency"
    assert window.transfer_concurrency_spin.value() == 2
    assert window.transfer_per_server_concurrency_label.text() == "Per server"
    assert window.transfer_per_server_concurrency_spin.value() == 2
    assert window.transfer_limit_label.text() == "Limit KB/s"
    assert window.transfer_limit_spin.value() == 0

    window.transfer_concurrency_spin.setValue(4)
    window.transfer_per_server_concurrency_spin.setValue(2)
    window.transfer_limit_spin.setValue(512)

    assert window.transfer_settings.max_concurrent == 4
    assert window.transfer_settings.max_concurrent_per_server == 2
    assert window.transfer_settings.bytes_per_second_limit == 512 * 1024


def test_transfer_center_renders_retry_and_failure_reason(qtbot, tmp_path) -> None:
    window = MainWindow(controller=FakeController())
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
        status=TransferStatus.RETRYING,
        retry_count=1,
        failure_reason="network down",
    )

    window.set_transfer_items([item])

    assert window.transfer_table.item(0, 7).text() == "network down"
    assert window.transfer_table.item(0, 8).text() == "Retrying"
    assert window.transfer_table.item(0, 8).background().color().isValid()


def test_transfer_center_shows_next_retry_time(qtbot, tmp_path) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)
    window.transfer_status_clock = lambda: datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
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
        status=TransferStatus.RETRYING,
        retry_count=1,
        failure_reason="network down",
        next_retry_at=datetime(2026, 6, 27, 12, 0, 2, tzinfo=UTC),
    )

    window.set_transfer_items([item])

    assert window.transfer_table.item(0, 8).text() == "Retrying in 2s"


def test_transfer_center_shows_relative_retry_countdown(qtbot, tmp_path) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)
    now = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
    window.transfer_status_clock = lambda: now
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
        status=TransferStatus.RETRYING,
        retry_count=1,
        failure_reason="network down",
        next_retry_at=datetime(2026, 6, 27, 12, 0, 2, tzinfo=UTC),
    )

    window.set_transfer_items([item])

    assert window.transfer_table.item(0, 8).text() == "Retrying in 2s"
    assert window.transfer_retry_countdown_timer.isActive()

    now = datetime(2026, 6, 27, 12, 0, 1, tzinfo=UTC)
    window._refresh_transfer_retry_countdowns()

    assert window.transfer_table.item(0, 8).text() == "Retrying in 1s"

    now = datetime(2026, 6, 27, 12, 0, 2, tzinfo=UTC)
    window._refresh_transfer_retry_countdowns()

    assert window.transfer_table.item(0, 8).text() == "Retrying now"
    assert not window.transfer_retry_countdown_timer.isActive()


def test_dragging_local_files_to_remote_queues_upload(qtbot, tmp_path) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    local_file = tmp_path / "upload.txt"
    local_file.write_text("hello", encoding="utf-8")
    window.remote_panel.path_edit.setText("/home/deploy")

    window._handle_remote_drop([local_file])

    assert controller.queued == [
        (local_file, PurePosixPath("/home/deploy/upload.txt"), Direction.UPLOAD)
    ]


def test_dragging_remote_rows_to_local_queues_download(qtbot, tmp_path) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    window.local_panel.path_edit.setText(str(tmp_path))
    window.remote_panel.path_edit.setText("/home/deploy")
    window.remote_panel.set_entries(
        [
            type(
                "Entry",
                (),
                {"name": "remote.txt", "is_dir": False, "size_bytes": 1, "modified_time": None},
            )(),
        ]
    )
    window.remote_panel.table.selectRow(1)

    window._handle_local_drop()

    assert controller.queued == [
        (PurePosixPath("/home/deploy/remote.txt"), tmp_path / "remote.txt", Direction.DOWNLOAD)
    ]


def test_main_window_renders_resource_snapshot_and_process_detail(qtbot) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    snapshot = ResourceSnapshot(
        cpu=CpuStats(percent=12.5),
        memory=MemoryStats(
            total_bytes=4 * 1024 * 1024 * 1024,
            used_bytes=1536 * 1024 * 1024,
            available_bytes=2560 * 1024 * 1024,
        ),
        disks=[
            DiskUsage(
                mount="/",
                total_bytes=80 * 1024 * 1024 * 1024,
                used_bytes=24 * 1024 * 1024 * 1024,
                available_bytes=56 * 1024 * 1024 * 1024,
            )
        ],
        network=NetworkStats(rx_bytes_per_sec=1536, tx_bytes_per_sec=2 * 1024 * 1024),
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
    qtbot.waitUntil(lambda: controller.resource_refreshes == 1, timeout=3000)
    qtbot.mouseClick(window.process_detail_button, Qt.MouseButton.LeftButton)
    window.set_process_detail(detail)

    assert window.cpu_value_label.text() == "12.5%"
    assert window.memory_value_label.text() == "1.5 GB / 4.0 GB"
    assert window.disk_value_label.text() == "/: 24.0 GB / 80.0 GB"
    assert window.network_value_label.text() == "RX 1.5 KB/s, TX 2.0 MB/s"
    assert window.process_table.item(0, 0).text() == "123"
    assert controller.resource_refreshes == 1
    assert controller.process_details == [123]
    assert "python app.py" in window.process_detail_label.text()
    assert "threads: 8" in window.process_detail_label.text()


def test_process_table_uses_full_row_activity_and_double_click_loads_detail(qtbot) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    window.set_resource_snapshot(
        ResourceSnapshot(
            cpu=CpuStats(percent=12.5),
            memory=MemoryStats(total_bytes=100, used_bytes=50, available_bytes=50),
            disks=[],
            network=NetworkStats(rx_bytes_per_sec=0, tx_bytes_per_sec=0),
            processes=[ProcessSummary(pid=123, user="deploy", name="python", cpu_percent=1.5, memory_percent=2.5)],
        )
    )

    assert window.process_table.selectionBehavior() == QAbstractItemView.SelectionBehavior.SelectRows
    assert window.process_table.selectionMode() == QAbstractItemView.SelectionMode.SingleSelection
    assert window.process_table.hasMouseTracking()
    assert window.process_table.itemDelegate().uses_full_row_activity
    window.process_table.set_hovered_row(0)
    assert window.process_table.hovered_row == 0

    window.process_table.cellDoubleClicked.emit(0, 2)

    assert controller.process_details == [123]


def test_process_table_uses_model_view_for_virtualized_rows(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)

    assert isinstance(window.process_table, QTableView)
    assert not isinstance(window.process_table, QTableWidget)
    assert window.process_table.model() is window.process_model


def test_process_context_and_detail_actions_stop_restart_and_copy_pid(qtbot) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    window.set_resource_snapshot(
        ResourceSnapshot(
            cpu=CpuStats(percent=12.5),
            memory=MemoryStats(total_bytes=100, used_bytes=50, available_bytes=50),
            disks=[],
            network=NetworkStats(rx_bytes_per_sec=0, tx_bytes_per_sec=0),
            processes=[ProcessSummary(pid=123, user="deploy", name="python", cpu_percent=1.5, memory_percent=2.5)],
        )
    )
    window.process_table.selectRow(0)

    window.process_stop_action.trigger()
    window.process_restart_action.trigger()
    window.process_copy_pid_action.trigger()

    assert controller.process_stops == [123]
    assert controller.process_restarts == [123]
    assert window.last_copied_text == "123"

    window.set_process_detail(
        ProcessDetail(
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
    )

    window.process_detail_stop_button.click()
    window.process_detail_restart_button.click()
    window.process_detail_copy_pid_button.click()

    assert controller.process_stops == [123, 123]
    assert controller.process_restarts == [123, 123]
    assert window.last_copied_text == "123"


def test_resource_monitor_has_time_range_and_process_filters(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)
    _use_english(window)

    assert [
        window.resource_time_range_selector.itemText(index)
        for index in range(window.resource_time_range_selector.count())
    ] == ["1m", "5m", "15m", "1h"]
    assert [
        window.process_sort_selector.itemText(index)
        for index in range(window.process_sort_selector.count())
    ] == ["CPU", "Memory", "PID", "Name"]
    assert window.process_filter_edit.placeholderText() == "Filter processes"

    window.set_resource_snapshot(
        ResourceSnapshot(
            cpu=CpuStats(percent=12.5),
            memory=MemoryStats(total_bytes=100, used_bytes=50, available_bytes=50),
            disks=[
                DiskUsage(mount="/", total_bytes=100, used_bytes=20, available_bytes=80),
                DiskUsage(mount="/data", total_bytes=200, used_bytes=80, available_bytes=120),
            ],
            network=NetworkStats(rx_bytes_per_sec=1024, tx_bytes_per_sec=2048),
            processes=[
                ProcessSummary(pid=3, user="root", name="nginx", cpu_percent=40.0, memory_percent=3.0),
                ProcessSummary(pid=9, user="deploy", name="python", cpu_percent=5.0, memory_percent=60.0),
            ],
        )
    )

    assert [
        window.disk_partition_selector.itemText(index)
        for index in range(window.disk_partition_selector.count())
    ] == ["All disks", "/", "/data"]

    window.disk_partition_selector.setCurrentText("/data")
    assert window.disk_value_label.text() == "/data: 80 B / 200 B"

    window.process_sort_selector.setCurrentText("Memory")
    assert window.process_table.item(0, 2).text() == "python"

    window.process_filter_edit.setText("ng")
    assert window.process_table.rowCount() == 1
    assert window.process_table.item(0, 2).text() == "nginx"


def test_resource_snapshot_updates_usage_chart_history(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)

    for index in range(3):
        window.set_resource_snapshot(
            ResourceSnapshot(
                cpu=CpuStats(percent=10 + index),
                memory=MemoryStats(total_bytes=100, used_bytes=20 + index, available_bytes=80 - index),
                disks=[DiskUsage(mount="/", total_bytes=200, used_bytes=50 + index, available_bytes=150 - index)],
                network=NetworkStats(
                    rx_bytes_per_sec=(index + 1) * 1024,
                    tx_bytes_per_sec=(index + 1) * 2048,
                ),
                processes=[],
            )
        )

    assert window.resource_chart.history == [
        {"cpu": 10.0, "memory": 20.0, "disk": 25.0, "network_rx": 1024.0, "network_tx": 2048.0},
        {"cpu": 11.0, "memory": 21.0, "disk": 25.5, "network_rx": 2048.0, "network_tx": 4096.0},
        {"cpu": 12.0, "memory": 22.0, "disk": 26.0, "network_rx": 3072.0, "network_tx": 6144.0},
    ]
    assert window.resource_content_splitter.widget(0) is window.process_table
    assert window.resource_content_splitter.widget(1) is window.resource_chart


def test_resource_usage_chart_exposes_network_series_and_sample_interaction(qtbot) -> None:
    chart = ResourceUsageChart(max_points=10)
    chart.resize(420, 220)
    qtbot.addWidget(chart)
    chart.show()
    qtbot.waitExposed(chart)

    for index in range(3):
        chart.add_snapshot(
            ResourceSnapshot(
                cpu=CpuStats(percent=10 + index * 20),
                memory=MemoryStats(total_bytes=100, used_bytes=20 + index * 20, available_bytes=80 - index * 20),
                disks=[DiskUsage(mount="/", total_bytes=100, used_bytes=30 + index * 20, available_bytes=70 - index * 20)],
                network=NetworkStats(
                    rx_bytes_per_sec=(index + 1) * 1024,
                    tx_bytes_per_sec=(index + 1) * 2048,
                ),
                processes=[],
            )
        )

    assert chart.series_keys() == ["cpu", "memory", "disk", "network_rx", "network_tx"]

    middle_point = chart.sample_point(1)
    _send_chart_mouse_move(chart, middle_point)

    assert chart.hovered_index == 1
    assert chart.active_index() == 1
    assert "RX 2.0 KB/s" in chart.detail_text()
    assert "TX 4.0 KB/s" in chart.detail_text()

    qtbot.mouseClick(chart, Qt.MouseButton.LeftButton, pos=middle_point)
    sample_two_point = chart.sample_point(2)
    _send_chart_mouse_move(chart, sample_two_point)

    assert chart.pinned_index == 1
    assert chart.active_index() == 1

    qtbot.mouseClick(chart, Qt.MouseButton.LeftButton, pos=middle_point)
    assert chart.pinned_index is None


def test_buttons_use_consistent_visual_roles(qtbot) -> None:
    window = MainWindow(controller=FakeController())
    qtbot.addWidget(window)

    assert window.connection_bar.connect_button.property("buttonRole") == "primary"
    assert window.local_panel.action_button.property("buttonRole") == "primary"
    assert window.remote_panel.action_button.property("buttonRole") == "primary"
    assert window.resource_refresh_button.property("buttonRole") == "neutral"
    assert window.process_detail_button.property("buttonRole") == "neutral"
    assert window.local_panel.refresh_button.property("buttonRole") == "neutral"
    assert window.remote_panel.refresh_button.property("buttonRole") == "neutral"
    assert window.pause_transfer_button.property("buttonRole") == "warning"
    assert window.retry_transfer_button.property("buttonRole") == "warning"
    window.set_agent_status(True, version="0.0.1")
    assert window.resource_install_agent_button.property("buttonRole") == "warning"
    assert window.connection_bar.disconnect_button.property("buttonRole") == "danger"
    assert window.cancel_transfer_button.property("buttonRole") == "danger"
    assert window.resource_uninstall_agent_button.property("buttonRole") == "danger"
    window._set_remote_loading(True, PurePosixPath("/tmp"))
    assert window.remote_panel.refresh_button.property("buttonRole") == "loading"
    assert not window.remote_panel.refresh_button.isEnabled()
