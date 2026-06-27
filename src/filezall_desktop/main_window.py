from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from PySide6.QtCore import (
    QAbstractTableModel,
    QEvent,
    QModelIndex,
    QObject,
    QPoint,
    QRect,
    Qt,
    QThread,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QActionGroup, QBrush, QColor, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from filezall_core import __version__
from filezall_core.app_paths import resolve_app_paths
from filezall_core.agent_deployment import classify_agent_error
from filezall_core.agent_status import AgentStatusViewModel, view_model_for_agent
from filezall_core.connection_recovery import ConnectionRecoveryState
from filezall_core.diagnostics import DiagnosticPackageBuilder
from filezall_core.log_service import TransferLogService
from filezall_core.models import (
    AuthMode,
    ConflictPolicy,
    Direction,
    Protocol,
    SiteProfile,
    TransferItem,
    TransferStatus,
)
from filezall_core.resource_models import ProcessDetail, ResourceSnapshot
from filezall_core.transfer_settings import TransferSettings
from filezall_desktop.assets import app_icon
from filezall_desktop.agent_status_card import AgentStatusCard
from filezall_desktop.conflict_dialog import choose_conflict_policy
from filezall_desktop.controller import MainWindowController, classify_connection_error
from filezall_desktop.i18n import (
    EN_LANGUAGE,
    LANGUAGE_LABELS,
    SYSTEM_LANGUAGE,
    ZH_CN_LANGUAGE,
    t,
)
from filezall_desktop.log_viewer import LogViewer
from filezall_desktop.onboarding import GettingStartedDialog
from filezall_desktop.site_manager import SiteManagerDialog
from filezall_desktop.theme import (
    DARK_THEME,
    LIGHT_THEME,
    SYSTEM_THEME,
    THEME_LABELS,
    hover_color_for_theme,
    selected_color_for_theme,
    stylesheet_for_theme,
)
from filezall_desktop.widgets import (
    ConnectionBar,
    FilePanel,
    HoverRowDelegate,
    HoverRowTableView,
    HoverRowTableWidget,
    ProcessTableModel,
)


class AgentActionWorker(QObject):
    progress = Signal(str)
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, action: Callable[[Callable[[str], None]], object]) -> None:
        super().__init__()
        self._action = action

    @Slot()
    def run(self) -> None:
        try:
            self.succeeded.emit(self._action(self.progress.emit))
        except Exception as exc:
            self.failed.emit(str(exc))


class ResourceRefreshWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, action: Callable[[], object]) -> None:
        super().__init__()
        self._action = action

    @Slot()
    def run(self) -> None:
        try:
            self.succeeded.emit(self._action())
        except Exception as exc:
            self.failed.emit(str(exc))


class RemoteDirectoryWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, action: Callable[[], object]) -> None:
        super().__init__()
        self._action = action

    @Slot()
    def run(self) -> None:
        try:
            self.succeeded.emit(self._action())
        except Exception as exc:
            self.failed.emit(str(exc))


class TransferOperationWorker(QObject):
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, label: str, action: Callable[[], None]) -> None:
        super().__init__()
        self._label = label
        self._action = action

    @Slot()
    def run(self) -> None:
        try:
            self._action()
            self.succeeded.emit(self._label)
        except Exception as exc:
            self.failed.emit(str(exc))


class SettingsDialog(QDialog):
    def __init__(self, window: "MainWindow") -> None:
        super().__init__(window)
        self._window = window
        self.setWindowTitle(window._text("settings.title"))
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.theme_selector = QComboBox(self)
        for theme_name, label in THEME_LABELS.items():
            self.theme_selector.addItem(label, theme_name)
        self.theme_selector.setCurrentIndex(
            max(self.theme_selector.findData(window.current_theme), 0)
        )

        self.language_selector = QComboBox(self)
        for language_name, label in LANGUAGE_LABELS.items():
            self.language_selector.addItem(label, language_name)
        self.language_selector.setCurrentIndex(
            max(self.language_selector.findData(window.current_language), 0)
        )

        self.density_selector = QComboBox(self)
        for density_name in ("compact", "standard", "comfortable"):
            self.density_selector.addItem(window._text(f"density.{density_name}"), density_name)
        self.density_selector.setCurrentIndex(
            max(self.density_selector.findData(window.file_list_density), 0)
        )

        self.concurrency_spin = QSpinBox(self)
        self.concurrency_spin.setRange(1, 16)
        self.concurrency_spin.setValue(window.transfer_settings.max_concurrent)

        self.per_server_concurrency_spin = QSpinBox(self)
        self.per_server_concurrency_spin.setRange(1, 16)
        self.per_server_concurrency_spin.setValue(
            window.transfer_settings.max_concurrent_per_server
            or window.transfer_settings.max_concurrent
        )

        self.limit_spin = QSpinBox(self)
        self.limit_spin.setRange(0, 1024 * 1024)
        limit = window.transfer_settings.bytes_per_second_limit or 0
        self.limit_spin.setValue(int(limit / 1024) if limit else 0)

        self.theme_label = QLabel(self)
        self.language_label = QLabel(self)
        self.density_label = QLabel(self)
        self.concurrency_label = QLabel(self)
        self.per_server_concurrency_label = QLabel(self)
        self.limit_label = QLabel(self)
        form.addRow(self.theme_label, self.theme_selector)
        form.addRow(self.language_label, self.language_selector)
        form.addRow(self.density_label, self.density_selector)
        form.addRow(self.concurrency_label, self.concurrency_spin)
        form.addRow(self.per_server_concurrency_label, self.per_server_concurrency_spin)
        form.addRow(self.limit_label, self.limit_spin)
        layout.addLayout(form)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.apply_button = self.button_box.button(QDialogButtonBox.StandardButton.Apply)
        self.button_box.accepted.connect(self._accept)
        self.button_box.rejected.connect(self.reject)
        self.apply_button.clicked.connect(self.apply_settings)
        layout.addWidget(self.button_box)
        self.retranslate()

    def apply_settings(self) -> None:
        self._window._apply_theme(str(self.theme_selector.currentData()))
        self._window._apply_language(str(self.language_selector.currentData()))
        self._window._apply_file_list_density(str(self.density_selector.currentData()))
        self._window.apply_transfer_settings(
            TransferSettings(
                max_concurrent=self.concurrency_spin.value(),
                max_concurrent_per_server=self.per_server_concurrency_spin.value(),
                bytes_per_second_limit=(
                    self.limit_spin.value() * 1024 if self.limit_spin.value() > 0 else None
                ),
            )
        )
        self.retranslate()

    def retranslate(self) -> None:
        self.setWindowTitle(self._window._text("settings.title"))
        self.theme_label.setText(self._window._text("settings.theme"))
        self.language_label.setText(self._window._text("settings.language"))
        self.density_label.setText(self._window._text("settings.density"))
        self.concurrency_label.setText(self._window._text("settings.concurrency"))
        self.per_server_concurrency_label.setText(self._window._text("settings.per_server"))
        self.limit_label.setText(self._window._text("settings.limit_kbps"))
        for density_name in ("compact", "standard", "comfortable"):
            index = self.density_selector.findData(density_name)
            if index >= 0:
                self.density_selector.setItemText(
                    index,
                    self._window._text(f"density.{density_name}"),
                )

    def _accept(self) -> None:
        self.apply_settings()
        self.accept()


class ResourceUsageChart(QWidget):
    _SERIES = [
        ("cpu", "CPU", QColor("#38bdf8")),
        ("memory", "MEM", QColor("#22c55e")),
        ("disk", "DISK", QColor("#f59e0b")),
        ("network_rx", "RX", QColor("#a78bfa")),
        ("network_tx", "TX", QColor("#fb7185")),
    ]

    def __init__(self, parent=None, max_points: int = 60) -> None:
        super().__init__(parent)
        self.max_points = max_points
        self.history: list[dict[str, float]] = []
        self.hovered_index: int | None = None
        self.pinned_index: int | None = None
        self.setMouseTracking(True)
        self.setMinimumWidth(260)
        self.setMinimumHeight(160)

    def add_snapshot(self, snapshot: ResourceSnapshot) -> None:
        memory_percent = _usage_percent(
            snapshot.memory.used_bytes,
            snapshot.memory.total_bytes,
        )
        disk_percent = 0.0
        if snapshot.disks:
            disk = snapshot.disks[0]
            disk_percent = _usage_percent(disk.used_bytes, disk.total_bytes)
        self.history.append(
            {
                "cpu": round(float(snapshot.cpu.percent), 1),
                "memory": round(memory_percent, 1),
                "disk": round(disk_percent, 1),
                "network_rx": float(snapshot.network.rx_bytes_per_sec),
                "network_tx": float(snapshot.network.tx_bytes_per_sec),
            }
        )
        if len(self.history) > self.max_points:
            self.history = self.history[-self.max_points :]
            self._trim_selection()
        self.update()

    def series_keys(self) -> list[str]:
        return [key for key, _label, _color in self._SERIES]

    def active_index(self) -> int | None:
        if self.pinned_index is not None:
            return self.pinned_index
        return self.hovered_index

    def detail_text(self) -> str:
        index = self.active_index()
        if index is None or not (0 <= index < len(self.history)):
            return ""
        row = self.history[index]
        return (
            f"Sample {index + 1}/{len(self.history)}  "
            f"CPU {row['cpu']:.1f}%  "
            f"MEM {row['memory']:.1f}%  "
            f"DISK {row['disk']:.1f}%  "
            f"RX {_human_bytes(row['network_rx'])}/s  "
            f"TX {_human_bytes(row['network_tx'])}/s"
        )

    def sample_point(self, index: int) -> QPoint:
        rect = self._plot_rect()
        if not self.history:
            return rect.center()
        bounded_index = max(0, min(index, len(self.history) - 1))
        width = max(rect.width(), 1)
        x = rect.left() + width * bounded_index / max(len(self.history) - 1, 1)
        return QPoint(int(x), rect.center().y())

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self._plot_rect()
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        painter.setPen(QPen(QColor("#64748b"), 1))
        painter.drawRect(rect)
        if not self.history:
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Waiting for resource data")
            return
        self._draw_grid(painter, rect)
        for name, _label, color in self._SERIES:
            self._draw_series(painter, rect, name, color)
        self._draw_active_sample(painter, rect)
        legend_x = rect.left()
        for name, label, color in self._SERIES:
            painter.setPen(QPen(color, 2))
            painter.drawLine(legend_x, rect.bottom() + 12, legend_x + 14, rect.bottom() + 12)
            painter.setPen(QPen(QColor("#64748b"), 1))
            painter.drawText(legend_x + 18, rect.bottom() + 16, label)
            legend_x += 58
        self._draw_detail_panel(painter, rect)

    def mouseMoveEvent(self, event) -> None:
        self.hovered_index = self._nearest_index(self._event_point(event))
        self.update()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            clicked_index = self._nearest_index(self._event_point(event))
            if clicked_index is not None:
                self.pinned_index = None if self.pinned_index == clicked_index else clicked_index
                self.update()
        super().mousePressEvent(event)

    def leaveEvent(self, event) -> None:
        self.hovered_index = None
        if self.pinned_index is None:
            self.update()
        super().leaveEvent(event)

    def _plot_rect(self) -> QRect:
        return self.rect().adjusted(12, 12, -12, -42)

    def _draw_grid(self, painter: QPainter, rect: QRect) -> None:
        painter.setPen(QPen(QColor("#263548"), 1))
        for step in range(1, 4):
            y = rect.top() + rect.height() * step / 4
            painter.drawLine(rect.left(), int(y), rect.right(), int(y))

    def _draw_series(self, painter: QPainter, rect: QRect, key: str, color: QColor) -> None:
        if len(self.history) < 2:
            return
        painter.setPen(QPen(color, 2))
        points = self._series_points(rect, key)
        for start, end in zip(points, points[1:]):
            painter.drawLine(start, end)

    def _draw_active_sample(self, painter: QPainter, rect: QRect) -> None:
        index = self.active_index()
        if index is None or not (0 <= index < len(self.history)):
            return
        x = self.sample_point(index).x()
        painter.setPen(QPen(QColor("#94a3b8"), 1, Qt.PenStyle.DashLine))
        painter.drawLine(x, rect.top(), x, rect.bottom())
        for key, _label, color in self._SERIES:
            points = self._series_points(rect, key)
            if index >= len(points):
                continue
            painter.setPen(QPen(color, 2))
            painter.setBrush(color)
            painter.drawEllipse(points[index], 3, 3)

    def _draw_detail_panel(self, painter: QPainter, rect: QRect) -> None:
        text = self.detail_text()
        if not text:
            return
        panel = QRect(rect.left() + 8, rect.top() + 8, min(rect.width() - 16, 360), 28)
        painter.setPen(QPen(QColor("#334155"), 1))
        painter.setBrush(QColor("#0f172a"))
        painter.drawRoundedRect(panel, 4, 4)
        painter.setPen(QPen(QColor("#dbeafe"), 1))
        painter.drawText(panel.adjusted(8, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter, text)

    def _series_points(self, rect: QRect, key: str) -> list[QPoint]:
        points: list[QPoint] = []
        width = max(rect.width(), 1)
        height = max(rect.height(), 1)
        scale = self._scale_for_key(key)
        for index, row in enumerate(self.history):
            x = rect.left() + width * index / max(len(self.history) - 1, 1)
            value = self._normalized_value(row[key], scale)
            y = rect.bottom() - height * value
            points.append(QPoint(int(x), int(y)))
        return points

    def _scale_for_key(self, key: str) -> float:
        if key.startswith("network_"):
            return max(
                1.0,
                max((row["network_rx"] for row in self.history), default=0.0),
                max((row["network_tx"] for row in self.history), default=0.0),
            )
        return 100.0

    def _normalized_value(self, value: float, scale: float) -> float:
        return max(0.0, min(float(value), scale)) / max(scale, 1.0)

    def _nearest_index(self, point: QPoint) -> int | None:
        if not self.history:
            return None
        rect = self._plot_rect()
        if point.x() <= rect.left():
            return 0
        if point.x() >= rect.right():
            return len(self.history) - 1
        distance = rect.width() / max(len(self.history) - 1, 1)
        return max(0, min(round((point.x() - rect.left()) / max(distance, 1)), len(self.history) - 1))

    def _trim_selection(self) -> None:
        if self.hovered_index is not None and self.hovered_index >= len(self.history):
            self.hovered_index = None
        if self.pinned_index is not None and self.pinned_index >= len(self.history):
            self.pinned_index = None

    def _event_point(self, event) -> QPoint:
        if hasattr(event, "position"):
            return event.position().toPoint()
        return event.pos()


class MainWindow(QMainWindow):
    transfer_items_requested = Signal(object)
    status_requested = Signal(str)
    log_requested = Signal(object)

    def __init__(
        self,
        controller=None,
        site_repository=None,
        credential_service=None,
        queue_service=None,
        local_directory_chooser=None,
        agent_install_confirmer=None,
        remember_secret_confirmer=None,
        log_file_chooser=None,
        diagnostic_file_chooser=None,
        diagnostics_logs_dir=None,
        rename_prompt=None,
        new_session_factory=None,
        agent_install_service=None,
        onboarding_settings=None,
        conflict_policy_prompt=None,
        delete_confirmer=None,
    ) -> None:
        super().__init__()
        self.log_service = TransferLogService()
        self.site_profiles = []
        self._session_windows = []
        self._site_secret_lookup = None
        self._local_directory_chooser = local_directory_chooser or _choose_local_directory
        self._agent_install_confirmer = agent_install_confirmer or _confirm_agent_install
        self._remember_secret_confirmer = remember_secret_confirmer
        self._log_file_chooser = log_file_chooser or _choose_log_file
        self._diagnostic_file_chooser = diagnostic_file_chooser or _choose_diagnostic_file
        self._diagnostics_logs_dir = Path(diagnostics_logs_dir) if diagnostics_logs_dir else resolve_app_paths().logs
        self._rename_prompt = rename_prompt or _prompt_rename
        self._new_session_factory = new_session_factory
        self._onboarding_settings = onboarding_settings
        self._conflict_policy_prompt = conflict_policy_prompt or choose_conflict_policy
        self._delete_confirmer = delete_confirmer or _confirm_delete
        self._site_repository = site_repository or getattr(controller, "_site_repository", None)
        self._should_confirm_remember_secret = controller is None
        self._heartbeat_failed_logged = False
        self._connection_attempt_count = 0
        self._connection_failure_count = 0
        self._last_connection_error: str | None = None
        self._heartbeat_failure_count = 0
        self._last_heartbeat_error: str | None = None
        self._connection_recovery = ConnectionRecoveryState()
        self.connection_recovery_clock: Callable[[], datetime] = lambda: datetime.now(UTC)
        self._agent_installed: bool | None = False
        self._agent_version: str | None = None
        self._agent_update_available = False
        self._connection_workers = []
        self._active_connection = None
        self._connection_running = False
        self._connection_test_running = False
        self._agent_workers = []
        self._active_agent_action = None
        self._resource_refresh_workers = []
        self._active_resource_refresh = None
        self._resource_refresh_running = False
        self._last_resource_snapshot: ResourceSnapshot | None = None
        self._current_process_detail_pid: int | None = None
        self._remote_directory_workers = []
        self._active_remote_directory_load = None
        self._remote_directory_loading = False
        self._remote_operation_workers = []
        self._heartbeat_workers = []
        self._active_heartbeat_check = None
        self._heartbeat_running = False
        self._process_sort_column = "CPU"
        self._process_sort_descending = True
        self._transfer_workers = []
        self.file_list_density = "standard"
        self.current_theme = SYSTEM_THEME
        self.current_language = SYSTEM_LANGUAGE
        self.last_copied_text = ""
        self.settings_dialog: SettingsDialog | None = None
        self._optimistic_transfer_items: list[TransferItem] = []
        self.transfer_settings = TransferSettings()
        self.getting_started_dialog: GettingStartedDialog | None = None
        self.site_manager_dialog: SiteManagerDialog | None = None
        self._rendered_transfer_items: list[TransferItem] = []
        self._pending_transfer_items: list[TransferItem] | None = None
        self.transfer_refresh_timer = QTimer(self)
        self.transfer_refresh_timer.setInterval(75)
        self.transfer_refresh_timer.setSingleShot(True)
        self.transfer_refresh_timer.timeout.connect(self._flush_pending_transfer_items)
        self.transfer_status_clock: Callable[[], datetime] = lambda: datetime.now(UTC)
        self.transfer_retry_countdown_timer = QTimer(self)
        self.transfer_retry_countdown_timer.setInterval(1_000)
        self.transfer_retry_countdown_timer.timeout.connect(self._refresh_transfer_retry_countdowns)
        self.transfer_items_requested.connect(
            self._set_transfer_items_on_ui,
            Qt.ConnectionType.QueuedConnection,
        )
        self.status_requested.connect(self._show_status_on_ui, Qt.ConnectionType.QueuedConnection)
        self.log_requested.connect(self._append_log_on_ui, Qt.ConnectionType.QueuedConnection)
        self.setWindowTitle("FileZall")
        self.setWindowIcon(app_icon())
        self.resize(1280, 800)
        self._build_session_menu()
        self._build_help_menu()
        self._build_settings_menu()
        self._build_logs_menu()
        self._build_toolbar()
        self._build_central_layout()
        self._build_shortcuts()
        self.local_panel.table.installEventFilter(self)
        self.remote_panel.table.installEventFilter(self)
        self._apply_button_roles()
        self._apply_file_list_density(self.file_list_density)
        self._apply_theme(SYSTEM_THEME)
        self._apply_language(SYSTEM_LANGUAGE)
        self.setStatusBar(QStatusBar(self))
        self.connection_state_label = QLabel("", self)
        self.connection_state_label.setFixedSize(12, 12)
        self.statusBar().addPermanentWidget(self.connection_state_label)
        self._set_connection_state("Idle", "grey")
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.setInterval(10_000)
        self.heartbeat_timer.timeout.connect(self._handle_heartbeat_tick)
        self.resource_refresh_timer = QTimer(self)
        self.resource_refresh_timer.setInterval(5_000)
        self.resource_refresh_timer.timeout.connect(self._handle_resource_refresh_tick)
        self.statusBar().showMessage(t(self.current_language, "status.ready"))
        self.controller = controller or MainWindowController(
            self,
            site_repository=site_repository,
            credential_service=credential_service,
            queue_service=queue_service,
            log_service=self.log_service,
            agent_install_service=agent_install_service,
        )
        self._connect_signals()
        self.controller.load_saved_sites()
        self._schedule_first_run_guide()

    def _build_session_menu(self) -> None:
        self.session_menu = QMenu("Session", self)
        self.menuBar().addMenu(self.session_menu)
        self.new_session_action = self.session_menu.addAction("New Session")
        self.new_session_action.setStatusTip("Open a new FileZall connection session")
        self.new_session_action.triggered.connect(self._handle_new_session_clicked)
        self.site_manager_action = self.session_menu.addAction("Site Manager")
        self.site_manager_action.setStatusTip("Manage saved FileZall sites")
        self.site_manager_action.triggered.connect(self._show_site_manager)

    def _build_help_menu(self) -> None:
        self.help_menu = QMenu("Help", self)
        self.menuBar().addMenu(self.help_menu)
        self.getting_started_action = self.help_menu.addAction("Getting Started")
        self.getting_started_action.setStatusTip("Show the first-use guide")
        self.getting_started_action.triggered.connect(self._show_getting_started)
        self.about_action = self.help_menu.addAction("About FileZall")
        self.about_action.setStatusTip("Show FileZall product information")
        self.about_action.triggered.connect(self._show_about)
        self.version_action = self.help_menu.addAction("Version")
        self.version_action.setStatusTip("Show the current FileZall version")
        self.version_action.triggered.connect(self._show_version)
        self.protocols_action = self.help_menu.addAction("Protocols")
        self.protocols_action.setStatusTip("Show supported transfer protocols")
        self.protocols_action.triggered.connect(self._show_protocols)
        self.commercial_action = self.help_menu.addAction("Commercial")
        self.commercial_action.setStatusTip("Show commercial licensing and support information")
        self.commercial_action.triggered.connect(self._show_commercial)

    def _show_site_manager(self) -> None:
        if self.site_manager_dialog is None:
            dialog = SiteManagerDialog(self._site_repository, self)
            dialog.sites_changed.connect(self.controller.load_saved_sites)
            self.site_manager_dialog = dialog
        else:
            self.site_manager_dialog.reload()
        self.site_manager_dialog.show()
        self.site_manager_dialog.raise_()
        self.site_manager_dialog.activateWindow()

    def _show_about(self) -> None:
        QMessageBox.information(
            self,
            "About FileZall",
            "FileZall is a desktop file transfer client with queued resumable transfers and optional Linux Agent acceleration.",
        )

    def _show_version(self) -> None:
        QMessageBox.information(self, "FileZall Version", f"FileZall {__version__}")

    def _show_protocols(self) -> None:
        QMessageBox.information(
            self,
            "Supported Protocols",
            "SFTP, FTP, FTPS, and FileZall Agent HTTP transfers are supported.",
        )

    def _show_commercial(self) -> None:
        QMessageBox.information(
            self,
            self._text("commercial.title"),
            self._text("commercial.body"),
        )

    def _show_getting_started(self) -> None:
        if self.getting_started_dialog is None:
            dialog = GettingStartedDialog(self._getting_started_texts(), self)
            dialog.focus_connection_requested.connect(self._focus_connection_setup)
            dialog.focus_local_requested.connect(self._focus_local_files)
            dialog.focus_remote_requested.connect(self._focus_remote_files)
            dialog.test_connection_requested.connect(self._handle_getting_started_test_connection)
            dialog.save_site_requested.connect(self._handle_getting_started_save_site)
            dialog.dismissed_changed.connect(self._set_onboarding_dismissed)
            self.getting_started_dialog = dialog
        else:
            self.getting_started_dialog.set_texts(self._getting_started_texts())
        self.getting_started_dialog.show()
        self.getting_started_dialog.raise_()
        self.getting_started_dialog.activateWindow()

    def _getting_started_texts(self) -> dict[str, str | list[str]]:
        return {
            "title": self._text("getting_started.title"),
            "intro": self._text("getting_started.intro"),
            "steps": [
                self._text("getting_started.step1"),
                self._text("getting_started.step2"),
                self._text("getting_started.step3"),
                self._text("getting_started.step4"),
                self._text("getting_started.step5"),
                self._text("getting_started.step6"),
            ],
            "focus_connection": self._text("getting_started.focus_connection"),
            "focus_local": self._text("getting_started.focus_local"),
            "focus_remote": self._text("getting_started.focus_remote"),
            "start_setup": self._text("getting_started.start_setup"),
            "test_connection": self._text("getting_started.test_connection"),
            "save_site": self._text("getting_started.save_site"),
            "close": self._text("getting_started.close"),
            "dismiss": self._text("getting_started.dismiss"),
        }

    def _schedule_first_run_guide(self) -> None:
        if self._onboarding_settings is None:
            return
        if self._onboarding_settings.get_bool("onboarding.dismissed", default=False):
            return
        QTimer.singleShot(0, self._show_getting_started)

    def _set_onboarding_dismissed(self, dismissed: bool) -> None:
        if self._onboarding_settings is not None:
            self._onboarding_settings.set_bool("onboarding.dismissed", dismissed)

    def _handle_getting_started_test_connection(self) -> None:
        if self.getting_started_dialog is None:
            return
        site = self._selected_saved_site() or self._site_from_fields()
        secret = self._secret_from_fields()
        self.getting_started_dialog.set_status(self._text("getting_started.testing_connection"))
        self.getting_started_dialog.set_connection_ready(False)
        self.append_log(f"Connection test requested for {site.host}:{site.port} as {site.username}")
        if hasattr(self.controller, "connect_for_window"):
            self._connection_test_running = True
            self._set_connection_state("Connecting", "goldenrod")
            self.connection_bar.connect_button.setEnabled(False)
            self._start_connection(site, secret, remember_secret=False)
            return
        try:
            self.controller.connect(site, secret, remember_secret=False)
        except Exception as exc:
            message = classify_connection_error(str(exc))
            self.getting_started_dialog.set_status(message)
            self.getting_started_dialog.set_connection_ready(False)
            self.append_log(f"Connection test failed: {message}")
            self._set_connection_state("Failed", "red")
            self.show_status(message)
            return
        self.getting_started_dialog.set_status(self._text("getting_started.connection_ok"))
        self.getting_started_dialog.set_connection_ready(True)
        self.append_log("Connection test passed")
        self._set_connection_state("Connected", "green")

    def _handle_getting_started_save_site(self) -> None:
        if self.getting_started_dialog is None:
            return
        site = self._selected_saved_site() or self._site_from_fields()
        secret = self._secret_from_fields()
        try:
            self.controller.connect(site, secret, remember_secret=True)
        except Exception as exc:
            message = classify_connection_error(str(exc))
            self.getting_started_dialog.set_status(message)
            self.append_log(f"Save site failed: {message}")
            self.show_status(message)
            return
        self.controller.load_saved_sites()
        self._set_onboarding_dismissed(True)
        self.getting_started_dialog.dismiss_checkbox.setChecked(True)
        self.getting_started_dialog.set_status(self._text("getting_started.site_saved"))
        self.append_log(f"Site saved: {site.host}:{site.port} as {site.username}")
        self.show_status(self._text("getting_started.site_saved"))

    def _focus_connection_setup(self) -> None:
        self._hide_getting_started_dialog()
        self.connection_bar.host_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _focus_local_files(self) -> None:
        self._hide_getting_started_dialog()
        self.local_panel.path_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _focus_remote_files(self) -> None:
        self._hide_getting_started_dialog()
        self.remote_panel.path_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def _hide_getting_started_dialog(self) -> None:
        if self.getting_started_dialog is not None:
            self.getting_started_dialog.hide()
        self.raise_()
        self.activateWindow()

    def _build_settings_menu(self) -> None:
        self.settings_menu = QMenu("Settings", self)
        self.menuBar().addMenu(self.settings_menu)
        self.settings_action = self.settings_menu.addAction("Open Settings")
        self.settings_action.triggered.connect(self._show_settings_dialog)
        self.settings_menu.addSeparator()
        self._build_theme_menu(parent_menu=self.settings_menu)
        self._build_language_menu(parent_menu=self.settings_menu)

    def _show_settings_dialog(self) -> None:
        if self.settings_dialog is None:
            self.settings_dialog = SettingsDialog(self)
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def _build_theme_menu(self, parent_menu: QMenu | None = None) -> None:
        self.theme_menu = QMenu("Theme", self)
        if parent_menu is None:
            self.menuBar().addMenu(self.theme_menu)
        else:
            parent_menu.addMenu(self.theme_menu)
        self.theme_action_group = QActionGroup(self)
        self.theme_action_group.setExclusive(True)
        self.system_theme_action = self._add_theme_action(SYSTEM_THEME)
        self.light_theme_action = self._add_theme_action(LIGHT_THEME)
        self.dark_theme_action = self._add_theme_action(DARK_THEME)
        self.theme_action_group.triggered.connect(self._handle_theme_action)
        self.theme_menu.addSeparator()
        self.density_action_group = QActionGroup(self)
        self.density_action_group.setExclusive(True)
        self.compact_density_action = self._add_density_action("compact", "density.compact")
        self.standard_density_action = self._add_density_action("standard", "density.standard")
        self.comfortable_density_action = self._add_density_action("comfortable", "density.comfortable")
        self.standard_density_action.setChecked(True)
        self.density_action_group.triggered.connect(self._handle_density_action)

    def _add_theme_action(self, theme_name: str):
        action = self.theme_menu.addAction(THEME_LABELS[theme_name])
        action.setCheckable(True)
        action.setData(theme_name)
        self.theme_action_group.addAction(action)
        return action

    def _handle_theme_action(self, action) -> None:
        self._apply_theme(action.data())

    def _add_density_action(self, density_name: str, text_key: str):
        action = self.theme_menu.addAction(t(EN_LANGUAGE, text_key))
        action.setCheckable(True)
        action.setData(density_name)
        action.setProperty("textKey", text_key)
        self.density_action_group.addAction(action)
        return action

    def _handle_density_action(self, action) -> None:
        self._apply_file_list_density(action.data())

    def _apply_file_list_density(self, density_name: str) -> None:
        sizes = {
            "compact": 24,
            "standard": 30,
            "comfortable": 36,
        }
        self.file_list_density = density_name if density_name in sizes else "standard"
        for action in getattr(self, "density_action_group", QActionGroup(self)).actions():
            action.setChecked(action.data() == self.file_list_density)
        size = sizes[self.file_list_density]
        for panel in (getattr(self, "local_panel", None), getattr(self, "remote_panel", None)):
            if panel is not None:
                panel.table.verticalHeader().setDefaultSectionSize(size)

    def _apply_theme(self, theme_name: str) -> None:
        self.current_theme = theme_name
        for action in self.theme_action_group.actions():
            action.setChecked(action.data() == theme_name)
        self.setStyleSheet(stylesheet_for_theme(theme_name))
        hover_color = hover_color_for_theme(theme_name)
        selected_color = selected_color_for_theme(theme_name)
        for table in self._full_row_activity_tables():
            table.set_full_row_hover_color(hover_color)
            table.set_full_row_selected_color(selected_color)

    def _full_row_activity_tables(self) -> list[HoverRowTableView | HoverRowTableWidget]:
        tables: list[HoverRowTableView | HoverRowTableWidget] = []
        for panel in (getattr(self, "local_panel", None), getattr(self, "remote_panel", None)):
            if panel is not None:
                tables.append(panel.table)
        process_table = getattr(self, "process_table", None)
        if isinstance(process_table, (HoverRowTableView, HoverRowTableWidget)):
            tables.append(process_table)
        return tables

    def _build_language_menu(self, parent_menu: QMenu | None = None) -> None:
        self.language_menu = QMenu("Language", self)
        if parent_menu is None:
            self.menuBar().addMenu(self.language_menu)
        else:
            parent_menu.addMenu(self.language_menu)
        self.language_action_group = QActionGroup(self)
        self.language_action_group.setExclusive(True)
        self.system_language_action = self._add_language_action(SYSTEM_LANGUAGE)
        self.english_language_action = self._add_language_action(EN_LANGUAGE)
        self.chinese_language_action = self._add_language_action(ZH_CN_LANGUAGE)
        self.language_action_group.triggered.connect(self._handle_language_action)

    def _add_language_action(self, language_name: str):
        action = self.language_menu.addAction(LANGUAGE_LABELS[language_name])
        action.setCheckable(True)
        action.setData(language_name)
        self.language_action_group.addAction(action)
        return action

    def _handle_language_action(self, action) -> None:
        self._apply_language(action.data())

    def _apply_language(self, language_name: str) -> None:
        self.current_language = language_name
        for action in self.language_action_group.actions():
            action.setChecked(action.data() == language_name)
        self._refresh_texts()

    def _text(self, key: str, **values) -> str:
        text = t(self.current_language, key)
        return text.format(**values) if values else text

    def _refresh_texts(self) -> None:
        self.session_menu.setTitle(self._text("menu.session"))
        self.new_session_action.setText(self._text("session.new"))
        self.site_manager_action.setText(self._text("session.site_manager"))
        self.site_manager_action.setStatusTip(self._text("session.site_manager_tip"))
        self.help_menu.setTitle(self._text("menu.help"))
        if hasattr(self, "settings_menu"):
            self.settings_menu.setTitle(self._text("menu.settings"))
            self.settings_action.setText(self._text("settings.open"))
        self.theme_menu.setTitle(self._text("menu.theme"))
        for action in getattr(self, "density_action_group", QActionGroup(self)).actions():
            action.setText(self._text(action.property("textKey")))
        self.language_menu.setTitle(self._text("menu.language"))
        if hasattr(self, "logs_menu"):
            self.logs_menu.setTitle(self._text("menu.logs"))
            self.export_logs_action.setText(self._text("logs.export"))
            self.export_diagnostics_action.setText(self._text("logs.export_diagnostics"))
        if hasattr(self, "log_viewer"):
            self.log_viewer.set_labels(
                copy_error=self._text("logs.copy_error"),
                export_logs=self._text("logs.export"),
                export_diagnostics=self._text("logs.export_diagnostics"),
            )

        self.getting_started_action.setText(self._text("help.getting_started"))
        self.getting_started_action.setStatusTip(self._text("help.getting_started_tip"))
        self.about_action.setText(self._text("help.about"))
        self.version_action.setText(self._text("help.version"))
        self.protocols_action.setText(self._text("help.protocols"))
        self.commercial_action.setText(self._text("help.commercial"))
        if self.getting_started_dialog is not None:
            self.getting_started_dialog.set_texts(self._getting_started_texts())
        if self.settings_dialog is not None:
            self.settings_dialog.retranslate()

        self.connection_bar.site_label.setText(self._text("connection.site"))
        self.connection_bar.host_edit.setPlaceholderText(self._text("connection.host"))
        self.connection_bar.username_edit.setPlaceholderText(self._text("connection.username"))
        self.connection_bar.secret_edit.setPlaceholderText(self._text("connection.password"))
        self.connection_bar.ssh_key_path_edit.setPlaceholderText(self._text("connection.ssh_key"))
        self.connection_bar.auth_mode_selector.setItemText(
            0,
            self._text("connection.password_mode"),
        )
        self.connection_bar.auth_mode_selector.setItemText(
            1,
            self._text("connection.ssh_key_mode"),
        )
        self.connection_bar.connect_button.setText(self._text("connection.connect"))
        self.connection_bar.disconnect_button.setText(self._text("connection.disconnect"))
        self._refresh_agent_action_text()

        if self.connection_bar.site_selector.count():
            self.connection_bar.site_selector.setItemText(0, self._text("site.quick"))

        if hasattr(self, "local_panel"):
            headers = [
                self._text("table.name"),
                self._text("table.size"),
                self._text("table.type"),
                self._text("table.modified"),
            ]
            common = {
                "refresh_label": self._text("files.refresh"),
                "choose_directory_tooltip": self._text("files.path_tooltip"),
                "headers": headers,
                "parent_label": self._text("table.parent"),
                "directory_label": self._text("table.directory"),
                "file_label": self._text("table.file"),
                "delete_label": self._text("context.delete"),
                "rename_label": self._text("context.rename"),
                "copy_path_label": self._text("context.copy_path"),
                "queue_label": self._text("context.queue"),
                "create_dir_label": self._text("context.create_dir"),
                "create_file_label": self._text("context.create_file"),
            }
            self.local_panel.set_texts(
                title=self._text("files.local"),
                action_label=self._text("files.upload"),
                transfer_label=self._text("files.upload"),
                path_button_text="...",
                **common,
            )
            self.remote_panel.set_texts(
                title=self._text("files.remote"),
                action_label=self._text("files.download"),
                transfer_label=self._text("files.download"),
                path_button_text=">",
                **common,
            )

        if hasattr(self, "transfer_table"):
            self.transfer_table.setHorizontalHeaderLabels(
                _transfer_headers()
            )
            self.transfer_center_label.setText(self._text("transfer.center"))
            self.transfer_concurrency_label.setText(self._text("transfer.concurrency"))
            self.transfer_per_server_concurrency_label.setText(
                self._text("transfer.per_server")
            )
            self.transfer_limit_label.setText(self._text("transfer.limit_kbps"))
            self.transfer_logs_label.setText(self._text("transfer.logs"))
            self.pause_transfer_button.setText(self._text("transfer.pause"))
            self.resume_transfer_button.setText(self._text("transfer.resume"))
            self.cancel_transfer_button.setText(self._text("transfer.cancel"))
            self.retry_transfer_button.setText(self._text("transfer.retry"))
            self.resource_refresh_button.setText(self._text("resource.refresh"))
            self.process_detail_button.setText(self._text("resource.show_process"))
            self.process_detail_clear_button.setText(self._text("process.clear"))
            self.resource_install_agent_button.setText(self._text("resource.install_agent"))
            self.resource_uninstall_agent_button.setText(self._text("resource.uninstall_agent"))
            self.resource_monitor_label.setText(self._text("resource.monitor"))
            self.resource_range_label.setText(self._text("resource.range"))
            self.resource_disk_label.setText(self._text("resource.disk_selector"))
            self.resource_sort_label.setText(self._text("resource.sort"))
            self.process_filter_edit.setPlaceholderText(self._text("resource.process_filter"))
            self.cpu_label.setText(self._text("resource.cpu"))
            self.memory_label.setText(self._text("resource.memory"))
            self.disk_label.setText(self._text("resource.disk"))
            self.network_label.setText(self._text("resource.network"))
            self.process_table.setHorizontalHeaderLabels(
                [
                    self._text("process.pid"),
                    self._text("process.user"),
                    self._text("process.name"),
                    self._text("process.cpu"),
                    self._text("process.memory"),
                    self._text("process.command"),
                ]
            )

    def _build_logs_menu(self) -> None:
        self.logs_menu = QMenu("Logs", self)
        self.menuBar().addMenu(self.logs_menu)
        self.export_logs_action = self.logs_menu.addAction("Export Logs")
        self.export_logs_action.setStatusTip("Export FileZall transfer and connection logs")
        self.export_logs_action.triggered.connect(self._export_logs)
        self.export_diagnostics_action = self.logs_menu.addAction("Export Diagnostics")
        self.export_diagnostics_action.setStatusTip("Export FileZall diagnostics package")
        self.export_diagnostics_action.triggered.connect(self._export_diagnostics)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Connection")
        toolbar.setMovable(False)
        self.connection_bar = ConnectionBar(self)
        toolbar.addWidget(self.connection_bar)
        self.addToolBar(toolbar)

    def _build_central_layout(self) -> None:
        root = QWidget(self)
        root_layout = QVBoxLayout(root)

        self.main_splitter = QSplitter(Qt.Orientation.Vertical, root)
        self.file_splitter = QSplitter(Qt.Orientation.Horizontal, self.main_splitter)
        self.local_panel = FilePanel("Local Files", "Upload", "...", self)
        self.remote_panel = FilePanel("Remote Files", "Download", ">", self)
        self.local_panel.set_placeholder_row("No directory loaded")
        self.remote_panel.set_placeholder_row("Not connected")
        self.file_splitter.addWidget(self.local_panel)
        self.file_splitter.addWidget(self.remote_panel)
        self.file_splitter.setSizes([640, 640])

        transfer_widget = QWidget(self.main_splitter)
        transfer_layout = QVBoxLayout(transfer_widget)
        self.transfer_model = TransferTableModel(
            transfer_widget,
            clock=lambda: self.transfer_status_clock(),
        )
        self.transfer_table = HoverRowTableView(transfer_widget)
        self.transfer_table.setModel(self.transfer_model)
        self.transfer_table.setHorizontalHeaderLabels(
            _transfer_headers()
        )
        self.transfer_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.transfer_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.transfer_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.transfer_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.transfer_table.horizontalHeader().setStretchLastSection(True)
        self.log_viewer = LogViewer(
            transfer_widget,
            export_logs_callback=self._export_logs,
            export_diagnostics_callback=self._export_diagnostics,
        )
        self.log_view = self.log_viewer
        self.transfer_splitter = QSplitter(Qt.Orientation.Vertical, transfer_widget)
        self.transfer_splitter.addWidget(self.transfer_table)
        self.transfer_splitter.addWidget(self.log_view)
        self.transfer_splitter.setSizes([130, 80])
        transfer_actions = QHBoxLayout()
        self.pause_transfer_button = QPushButton("Pause", root)
        self.resume_transfer_button = QPushButton("Resume", root)
        self.cancel_transfer_button = QPushButton("Cancel", root)
        self.retry_transfer_button = QPushButton("Retry", root)
        self.transfer_center_label = QLabel("Transfer Center", root)
        self.transfer_concurrency_label = QLabel("Concurrency", root)
        self.transfer_concurrency_spin = QSpinBox(root)
        self.transfer_concurrency_spin.setRange(1, 16)
        self.transfer_concurrency_spin.setValue(self.transfer_settings.max_concurrent)
        self.transfer_per_server_concurrency_label = QLabel("Per server", root)
        self.transfer_per_server_concurrency_spin = QSpinBox(root)
        self.transfer_per_server_concurrency_spin.setRange(1, 16)
        self.transfer_per_server_concurrency_spin.setValue(
            self.transfer_settings.max_concurrent_per_server
            or self.transfer_settings.max_concurrent
        )
        self.transfer_limit_label = QLabel("Limit KB/s", root)
        self.transfer_limit_spin = QSpinBox(root)
        self.transfer_limit_spin.setRange(0, 1024 * 1024)
        self.transfer_limit_spin.setValue(0)
        transfer_actions.addWidget(self.transfer_center_label)
        for settings_widget in (
            self.transfer_concurrency_label,
            self.transfer_concurrency_spin,
            self.transfer_per_server_concurrency_label,
            self.transfer_per_server_concurrency_spin,
            self.transfer_limit_label,
            self.transfer_limit_spin,
        ):
            settings_widget.hide()
        transfer_actions.addStretch(1)
        transfer_actions.addWidget(self.pause_transfer_button)
        transfer_actions.addWidget(self.resume_transfer_button)
        transfer_actions.addWidget(self.cancel_transfer_button)
        transfer_actions.addWidget(self.retry_transfer_button)
        self.monitoring_status_label = QLabel("", transfer_widget)
        self.monitoring_status_label.hide()
        self.transfer_summary_label = QLabel("", transfer_widget)

        transfer_layout.addLayout(transfer_actions, stretch=0)
        transfer_layout.addWidget(self.transfer_summary_label, stretch=0)
        transfer_layout.addWidget(self.monitoring_status_label, stretch=0)
        self.transfer_logs_label = QLabel("Transfer Logs", transfer_widget)
        transfer_layout.addWidget(self.transfer_logs_label, stretch=0)
        transfer_layout.addWidget(self.transfer_splitter, stretch=1)

        resource_widget = QWidget(self.main_splitter)
        resource_layout = QVBoxLayout(resource_widget)
        resource_actions = QHBoxLayout()
        self.resource_refresh_button = QPushButton("Refresh Resources", root)
        self.process_detail_button = QPushButton("Process Detail", root)
        self.agent_status_label = QLabel("", resource_widget)
        self.resource_install_agent_button = QPushButton("Install Agent", resource_widget)
        self.resource_uninstall_agent_button = QPushButton("Uninstall Agent", resource_widget)
        self.resource_install_agent_button.hide()
        self.resource_uninstall_agent_button.hide()
        self.resource_monitor_label = QLabel("Resource Monitor", root)
        self.agent_status_card = AgentStatusCard(resource_widget)
        self.agent_status_card.show_danger_actions = False
        self.agent_status_card.show_operation_steps = False
        resource_actions.addWidget(self.resource_monitor_label)
        resource_actions.addWidget(self.agent_status_label)
        resource_actions.addStretch(1)
        resource_actions.addWidget(self.resource_install_agent_button)
        resource_actions.addWidget(self.resource_uninstall_agent_button)
        resource_actions.addWidget(self.resource_refresh_button)
        resource_actions.addWidget(self.process_detail_button)

        resource_controls = QHBoxLayout()
        self.resource_time_range_selector = QComboBox(resource_widget)
        self.resource_time_range_selector.addItems(["1m", "5m", "15m", "1h"])
        self.resource_time_range_selector.setCurrentText("5m")
        self.disk_partition_selector = QComboBox(resource_widget)
        self.disk_partition_selector.addItem(self._text("resource.all_disks"))
        self.process_sort_selector = QComboBox(resource_widget)
        self.process_sort_selector.addItems(["CPU", "Memory", "PID", "Name"])
        self.process_filter_edit = QLineEdit(resource_widget)
        self.process_filter_edit.setPlaceholderText(self._text("resource.process_filter"))
        self.resource_range_label = QLabel("Range", resource_widget)
        self.resource_disk_label = QLabel("Disk", resource_widget)
        self.resource_sort_label = QLabel("Sort", resource_widget)
        resource_controls.addWidget(self.resource_range_label)
        resource_controls.addWidget(self.resource_time_range_selector)
        resource_controls.addWidget(self.resource_disk_label)
        resource_controls.addWidget(self.disk_partition_selector)
        resource_controls.addWidget(self.resource_sort_label)
        resource_controls.addWidget(self.process_sort_selector)
        resource_controls.addWidget(self.process_filter_edit, stretch=1)

        resource_values = QHBoxLayout()
        self.cpu_value_label = QLabel("0.0%", root)
        self.memory_value_label = QLabel("0 / 0 bytes", root)
        self.disk_value_label = QLabel("", root)
        self.network_value_label = QLabel("RX 0 B/s, TX 0 B/s", root)
        self.cpu_label = QLabel("CPU", root)
        self.memory_label = QLabel("Memory", root)
        self.disk_label = QLabel("Disk", root)
        self.network_label = QLabel("Network", root)
        resource_values.addWidget(self.cpu_label)
        resource_values.addWidget(self.cpu_value_label)
        resource_values.addWidget(self.memory_label)
        resource_values.addWidget(self.memory_value_label)
        resource_values.addWidget(self.disk_label)
        resource_values.addWidget(self.disk_value_label)
        resource_values.addWidget(self.network_label)
        resource_values.addWidget(self.network_value_label)

        self.process_model = ProcessTableModel(root)
        self.process_table = HoverRowTableView(root)
        self.process_table.setModel(self.process_model)
        self.process_table.setItemDelegate(HoverRowDelegate(self.process_table))
        self.process_table.setHorizontalHeaderLabels(["PID", "User", "Name", "CPU", "Memory", "Command"])
        self.process_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.process_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.process_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.process_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.process_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.process_table.horizontalHeader().setStretchLastSection(True)
        self.process_table.horizontalHeader().setSortIndicatorShown(True)
        self.process_table.horizontalHeader().setSortIndicator(3, Qt.SortOrder.DescendingOrder)
        self.process_menu = QMenu(self.process_table)
        self.process_detail_action = self.process_menu.addAction("Process Detail")
        self.process_stop_action = self.process_menu.addAction("Stop Process")
        self.process_restart_action = self.process_menu.addAction("Restart Process")
        self.process_copy_pid_action = self.process_menu.addAction("Copy Process ID")
        self.process_detail_label = QLabel("", root)
        self.process_detail_stop_button = QPushButton("Stop Process", root)
        self.process_detail_restart_button = QPushButton("Restart Process", root)
        self.process_detail_copy_pid_button = QPushButton("Copy Process ID", root)
        self.process_detail_clear_button = QPushButton("Clear", root)
        self.process_detail_actions = QWidget(root)
        process_detail_actions_layout = QHBoxLayout(self.process_detail_actions)
        process_detail_actions_layout.setContentsMargins(0, 0, 0, 0)
        process_detail_actions_layout.addWidget(self.process_detail_label, stretch=1)
        process_detail_actions_layout.addWidget(self.process_detail_clear_button)
        process_detail_actions_layout.addWidget(self.process_detail_copy_pid_button)
        process_detail_actions_layout.addWidget(self.process_detail_restart_button)
        process_detail_actions_layout.addWidget(self.process_detail_stop_button)
        self.process_detail_actions.hide()
        self.resource_chart = ResourceUsageChart(root)
        self.resource_content_splitter = QSplitter(Qt.Orientation.Horizontal, resource_widget)
        self.resource_content_splitter.addWidget(self.process_table)
        self.resource_content_splitter.addWidget(self.resource_chart)
        self.resource_content_splitter.setStretchFactor(0, 1)
        self.resource_content_splitter.setStretchFactor(1, 1)
        self.resource_content_splitter.setSizes([600, 600])

        resource_layout.addLayout(resource_actions, stretch=0)
        resource_layout.addWidget(self.agent_status_card, stretch=0)
        resource_layout.addLayout(resource_controls, stretch=0)
        resource_layout.addLayout(resource_values, stretch=0)
        resource_layout.addWidget(self.resource_content_splitter, stretch=1)
        resource_layout.addWidget(self.process_detail_actions, stretch=0)

        self.main_splitter.addWidget(self.file_splitter)
        self.main_splitter.addWidget(transfer_widget)
        self.main_splitter.addWidget(resource_widget)
        self.main_splitter.setSizes([420, 190, 190])
        root_layout.addWidget(self.main_splitter)
        self.setCentralWidget(root)

    def _build_shortcuts(self) -> None:
        shortcuts = [
            ("Ctrl+A", self._shortcut_select_all),
            ("F5", self._shortcut_refresh),
            ("Delete", self._shortcut_delete),
            ("Return", self._shortcut_enter),
            ("Enter", self._shortcut_enter),
            ("Backspace", self._shortcut_parent),
        ]
        self._file_panel_shortcuts = []
        for sequence, handler in shortcuts:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
            shortcut.activated.connect(handler)
            self._file_panel_shortcuts.append(shortcut)

    def _active_file_panel(self):
        focus_widget = QApplication.focusWidget()
        if focus_widget is not None:
            if self.remote_panel.isAncestorOf(focus_widget) or focus_widget is self.remote_panel:
                return self.remote_panel
            if self.local_panel.isAncestorOf(focus_widget) or focus_widget is self.local_panel:
                return self.local_panel
        return self.local_panel

    def _shortcut_select_all(self) -> None:
        self._active_file_panel().table.selectAll()

    def _shortcut_refresh(self) -> None:
        if self._active_file_panel() is self.remote_panel:
            self._handle_remote_refresh_clicked()
            return
        self._handle_local_refresh_clicked()

    def _shortcut_delete(self) -> None:
        if self._active_file_panel() is self.remote_panel:
            self._handle_remote_delete_action()
            return
        self._handle_local_delete_action()

    def _shortcut_enter(self) -> None:
        panel = self._active_file_panel()
        rows = panel.selected_rows()
        if not rows:
            return
        row = rows[0]
        if panel is self.remote_panel:
            self._handle_remote_double_clicked(row, 0)
            return
        self._handle_local_double_clicked(row, 0)

    def _shortcut_parent(self) -> None:
        if self._active_file_panel() is self.remote_panel:
            self._load_remote_directory(self._remote_parent())
            return
        self._load_local_directory(self._local_parent())

    def eventFilter(self, watched, event) -> bool:
        if (
            watched in {getattr(self.local_panel, "table", None), getattr(self.remote_panel, "table", None)}
            and event.type() == QEvent.Type.KeyPress
        ):
            key = event.key()
            modifiers = event.modifiers()
            if key == Qt.Key.Key_F5:
                self._shortcut_refresh()
                return True
            if key == Qt.Key.Key_Delete:
                self._shortcut_delete()
                return True
            if key in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
                self._shortcut_enter()
                return True
            if key == Qt.Key.Key_Backspace:
                self._shortcut_parent()
                return True
            if key == Qt.Key.Key_A and modifiers & Qt.KeyboardModifier.ControlModifier:
                self._shortcut_select_all()
                return True
        return super().eventFilter(watched, event)

    def _apply_button_roles(self) -> None:
        role_map = {
            self.connection_bar.connect_button: "primary",
            self.connection_bar.disconnect_button: "danger",
            self.connection_bar.install_agent_button: "warning",
            self.local_panel.refresh_button: "neutral",
            self.remote_panel.refresh_button: "neutral",
            self.local_panel.action_button: "primary",
            self.remote_panel.action_button: "primary",
            self.pause_transfer_button: "warning",
            self.resume_transfer_button: "primary",
            self.cancel_transfer_button: "danger",
            self.retry_transfer_button: "warning",
            self.resource_install_agent_button: "primary",
            self.resource_uninstall_agent_button: "danger",
            self.resource_refresh_button: "neutral",
            self.process_detail_button: "neutral",
            self.process_detail_copy_pid_button: "neutral",
            self.process_detail_clear_button: "neutral",
            self.process_detail_restart_button: "warning",
            self.process_detail_stop_button: "danger",
        }
        for button, role in role_map.items():
            button.setProperty("buttonRole", role)

    def set_local_entries(self, entries) -> None:
        self.local_panel.set_entries(entries)

    def set_local_directory_path(self, path) -> None:
        self.local_panel.path_edit.setText(str(path))
        self.local_panel.path_edit.add_history(str(path))

    def set_remote_entries(self, entries, path) -> None:
        self.remote_panel.path_edit.setText(str(path or ""))
        if path:
            self.remote_panel.path_edit.add_history(str(path))
        self.remote_panel.set_entries(entries)

    def show_status(self, message: str) -> None:
        if QThread.currentThread() is not self.thread():
            self.status_requested.emit(message)
            return
        self._show_status_on_ui(message)

    @Slot(str)
    def _show_status_on_ui(self, message: str) -> None:
        self.statusBar().showMessage(message)

    def append_log(
        self,
        message: str,
        *,
        category: str | None = None,
        level: str | None = None,
    ) -> None:
        if QThread.currentThread() is not self.thread():
            self.log_requested.emit((message, category, level))
            return
        self._append_log_on_ui((message, category, level))

    @Slot(object)
    def _append_log_on_ui(self, payload) -> None:
        message, category, level = payload
        resolved_category = category or _log_category_for_message(message)
        resolved_level = level or ("error" if resolved_category == "error" else "info")
        entry = self.log_service.append(
            message,
            category=resolved_category,
            level=resolved_level,
        )
        self.log_viewer.add_record(entry)

    def _export_logs(self) -> None:
        selected = self._log_file_chooser(self)
        if not selected:
            return
        self.log_service.export(Path(selected))
        self.show_status(f"Exported logs to {selected}")

    def _export_diagnostics(self) -> None:
        selected = self._diagnostic_file_chooser(self)
        if not selected:
            return
        DiagnosticPackageBuilder(
            log_service=self.log_service,
            logs_dir=self._diagnostics_logs_dir,
            state_provider=self._diagnostic_state_snapshot,
        ).build(Path(selected))
        self.show_status(f"Exported diagnostics to {selected}")

    def _diagnostic_state_snapshot(self) -> dict:
        transfer_items = list(self._optimistic_transfer_items)
        records = self.log_service.records()
        errors = [record for record in records if record.level == "error" or record.category == "error"]
        status_counts = Counter(item.status.value for item in transfer_items)
        retry_diagnostics = _transfer_retry_diagnostics(
            transfer_items,
            now=self.transfer_status_clock(),
        )
        recovery = self._connection_recovery.snapshot()
        return {
            "connection": {
                "state": self.connection_state_label.property("connectionState"),
                "tooltip": self.connection_state_label.toolTip(),
                "running": self._connection_running,
                "heartbeat_timer_active": self.heartbeat_timer.isActive(),
                "heartbeat_interval_ms": self.heartbeat_timer.interval(),
                "attempts": self._connection_attempt_count,
                "failures": self._connection_failure_count,
                "last_error": self._last_connection_error,
                "heartbeat_failures": self._heartbeat_failure_count,
                "last_heartbeat_error": self._last_heartbeat_error,
                "recovery": {
                    "state": recovery.state,
                    "attempt": recovery.attempt,
                    "next_retry_at": recovery.next_retry_at.isoformat()
                    if recovery.next_retry_at
                    else None,
                    "last_error": recovery.last_error,
                },
            },
            "resource_refresh": {
                "running": self._resource_refresh_running,
                "timer_active": self.resource_refresh_timer.isActive(),
                "interval_ms": self.resource_refresh_timer.interval(),
                "worker_count": len(self._resource_refresh_workers),
                "snapshot_available": self._last_resource_snapshot is not None,
                "chart_samples": len(self.resource_chart.history),
            },
            "transfer_queue": {
                "total": len(transfer_items),
                "by_status": dict(sorted(status_counts.items())),
                "pending_render": self._pending_transfer_items is not None,
                "rendered_rows": len(self._rendered_transfer_items),
                "summary": self.transfer_summary_label.text(),
                "retrying": retry_diagnostics["retrying"],
                "failures": retry_diagnostics["failures"],
            },
            "logs": {
                "total_records": len(records),
                "error_count": len(errors),
                "recent_errors": [_diagnostic_log_record(record) for record in errors[-10:]],
                "recent_records": [_diagnostic_log_record(record) for record in records[-20:]],
            },
            "agent": {
                "installed": self._agent_installed,
                "version": self._agent_version,
                "update_available": self._agent_update_available,
            },
            "ui": {
                "theme": self.current_theme,
                "language": self.current_language,
                "file_list_density": self.file_list_density,
                "local_rows": self.local_panel.table.rowCount(),
                "remote_rows": self.remote_panel.table.rowCount(),
                "process_rows": self.process_table.rowCount(),
            },
        }

    def set_monitoring_status(self, message: str) -> None:
        self.monitoring_status_label.setText(message)
        self.monitoring_status_label.hide()
        self.resource_monitor_label.setToolTip(message)
        if "Agent" in message:
            self.set_agent_status(False)
            self.resource_install_agent_button.show()
            self.resource_uninstall_agent_button.hide()
        else:
            self.agent_status_label.setText("")
            self.resource_install_agent_button.hide()
            self.resource_uninstall_agent_button.hide()

    def set_agent_status_model(self, model: AgentStatusViewModel) -> None:
        self.agent_status_card.set_status(model)

    def set_agent_status(self, installed: bool | None, version: str | None = None) -> None:
        self._agent_installed = installed
        if version is not None:
            self._agent_version = version
        elif installed is not True:
            self._agent_version = None
        self._agent_update_available = (
            installed is True
            and self._agent_version is not None
            and _version_is_older(self._agent_version, __version__)
        )
        self._refresh_agent_action_text()
        self.set_agent_status_model(
            view_model_for_agent(
                installed,
                version=self._agent_version,
                current_version=__version__,
                update_available=self._agent_update_available,
            )
        )
        if installed is None:
            self.agent_status_label.setText("Checking Agent...")
            self.resource_install_agent_button.show()
            self.resource_uninstall_agent_button.hide()
        elif installed:
            if self._agent_update_available:
                self.agent_status_label.setText(
                    f"Agent update available v{self._agent_version} -> v{__version__}"
                )
                self.resource_install_agent_button.setText(self._text("resource.update_agent"))
                self.resource_install_agent_button.setProperty("buttonRole", "warning")
                self.resource_install_agent_button.show()
                self.resource_uninstall_agent_button.show()
                return
            suffix = f" v{self._agent_version}" if self._agent_version else ""
            self.agent_status_label.setText(f"Agent installed{suffix}")
            self.resource_install_agent_button.setText(self._text("resource.install_agent"))
            self.resource_install_agent_button.setProperty("buttonRole", "primary")
            self.resource_install_agent_button.hide()
            self.resource_uninstall_agent_button.show()
        else:
            self.agent_status_label.setText("Agent not installed")
            self.resource_install_agent_button.setText(self._text("resource.install_agent"))
            self.resource_install_agent_button.setProperty("buttonRole", "primary")
            self.resource_install_agent_button.show()
            self.resource_uninstall_agent_button.hide()

    def set_agent_version(self, version: str | None) -> None:
        self._agent_version = version
        if self._agent_installed is True:
            self.set_agent_status(True, version=version)

    def set_transfer_items(self, items: list[TransferItem]) -> None:
        if QThread.currentThread() is not self.thread():
            self.transfer_items_requested.emit(list(items))
            return
        self._set_transfer_items_on_ui(items)

    @Slot(object)
    def _set_transfer_items_on_ui(self, items) -> None:
        items = list(items)
        self._optimistic_transfer_items = items
        self.transfer_summary_label.setText(_transfer_summary_text(items))
        if self._should_render_transfer_items_immediately(items):
            self.transfer_refresh_timer.stop()
            self._pending_transfer_items = None
            self._render_transfer_items(items)
            return
        self._pending_transfer_items = items
        if not self.transfer_refresh_timer.isActive():
            self.transfer_refresh_timer.start()

    def _should_render_transfer_items_immediately(self, items: list[TransferItem]) -> bool:
        if not self._rendered_transfer_items:
            return True
        if len(items) != len(self._rendered_transfer_items):
            return True
        rendered_keys = [_transfer_render_key(item) for item in self._rendered_transfer_items]
        next_keys = [_transfer_render_key(item) for item in items]
        if rendered_keys != next_keys:
            return True
        return any(_is_terminal_transfer_status(item.status) for item in items)

    def _flush_pending_transfer_items(self) -> None:
        if self._pending_transfer_items is None:
            return
        items = self._pending_transfer_items
        self._pending_transfer_items = None
        self._render_transfer_items(items)

    def _render_transfer_items(self, items: list[TransferItem]) -> None:
        self._rendered_transfer_items = list(items)
        self.transfer_model.set_items(items)
        self._sync_transfer_retry_countdown_timer()

    def _refresh_transfer_retry_countdowns(self) -> None:
        if not self._rendered_transfer_items:
            self.transfer_retry_countdown_timer.stop()
            return
        now = self.transfer_status_clock()
        self.transfer_model.refresh_statuses()
        self._sync_transfer_retry_countdown_timer(now=now)

    def _sync_transfer_retry_countdown_timer(self, now: datetime | None = None) -> None:
        now = now or self.transfer_status_clock()
        has_future_retry = any(
            item.status is TransferStatus.RETRYING
            and item.next_retry_at is not None
            and item.next_retry_at > now
            for item in self._rendered_transfer_items
        )
        if has_future_retry and not self.transfer_retry_countdown_timer.isActive():
            self.transfer_retry_countdown_timer.start()
        elif not has_future_retry and self.transfer_retry_countdown_timer.isActive():
            self.transfer_retry_countdown_timer.stop()

    def set_resource_snapshot(self, snapshot: ResourceSnapshot) -> None:
        self._last_resource_snapshot = snapshot
        self.cpu_value_label.setText(f"{snapshot.cpu.percent:.1f}%")
        self.memory_value_label.setText(
            f"{_human_bytes(snapshot.memory.used_bytes)} / {_human_bytes(snapshot.memory.total_bytes)}"
        )
        self._update_disk_partition_selector(snapshot)
        self._refresh_resource_disk_text()
        self.network_value_label.setText(
            f"RX {_human_bytes(snapshot.network.rx_bytes_per_sec)}/s, "
            f"TX {_human_bytes(snapshot.network.tx_bytes_per_sec)}/s"
        )
        self.resource_chart.add_snapshot(snapshot)
        self._refresh_process_table()

    def _update_disk_partition_selector(self, snapshot: ResourceSnapshot) -> None:
        current = self.disk_partition_selector.currentText()
        items = ["All disks"] + [disk.mount for disk in snapshot.disks]
        existing = [
            self.disk_partition_selector.itemText(index)
            for index in range(self.disk_partition_selector.count())
        ]
        if existing == items:
            return
        self.disk_partition_selector.blockSignals(True)
        self.disk_partition_selector.clear()
        self.disk_partition_selector.addItems(items)
        self.disk_partition_selector.setCurrentText(current if current in items else "All disks")
        self.disk_partition_selector.blockSignals(False)

    def _refresh_resource_disk_text(self) -> None:
        if self._last_resource_snapshot is None:
            return
        selected = self.disk_partition_selector.currentText()
        self.disk_value_label.setText(_disk_text(self._last_resource_snapshot, mount=selected))

    def _refresh_process_table(self) -> None:
        if self._last_resource_snapshot is None:
            return
        processes = self._filtered_sorted_processes(self._last_resource_snapshot.processes)
        self.process_model.set_processes(processes)
        self.process_table.clearSelection()
        self.process_table.set_hovered_row(-1)

    def _filtered_sorted_processes(self, processes):
        filter_text = self.process_filter_edit.text().strip().lower()
        if filter_text:
            processes = [
                process
                for process in processes
                if filter_text in str(process.pid).lower()
                or filter_text in process.user.lower()
                or filter_text in process.name.lower()
                or filter_text in getattr(process, "command_line", "").lower()
            ]
        sort_mode = self._process_sort_column
        if sort_mode == "Memory":
            return sorted(
                processes,
                key=lambda process: process.memory_percent,
                reverse=self._process_sort_descending,
            )
        if sort_mode == "PID":
            return sorted(
                processes,
                key=lambda process: process.pid,
                reverse=self._process_sort_descending,
            )
        if sort_mode == "Name":
            return sorted(
                processes,
                key=lambda process: process.name.lower(),
                reverse=self._process_sort_descending,
            )
        if sort_mode == "User":
            return sorted(
                processes,
                key=lambda process: process.user.lower(),
                reverse=self._process_sort_descending,
            )
        if sort_mode == "Command":
            return sorted(
                processes,
                key=lambda process: getattr(process, "command_line", "").lower(),
                reverse=self._process_sort_descending,
            )
        return sorted(
            processes,
            key=lambda process: process.cpu_percent,
            reverse=self._process_sort_descending,
        )

    def _set_process_sort(self, column: str, descending: bool) -> None:
        self._process_sort_column = column
        self._process_sort_descending = descending
        indicator_column = {
            "PID": 0,
            "User": 1,
            "Name": 2,
            "CPU": 3,
            "Memory": 4,
            "Command": 5,
        }.get(column, 3)
        order = Qt.SortOrder.DescendingOrder if descending else Qt.SortOrder.AscendingOrder
        self.process_table.horizontalHeader().setSortIndicator(indicator_column, order)
        self._refresh_process_table()

    def _handle_process_header_clicked(self, section: int) -> None:
        column = {
            0: "PID",
            1: "User",
            2: "Name",
            3: "CPU",
            4: "Memory",
            5: "Command",
        }.get(section, "CPU")
        default_descending = column in {"CPU", "Memory"}
        descending = default_descending
        if self._process_sort_column == column:
            descending = not self._process_sort_descending
        self._set_process_sort(column, descending)

    def _handle_process_sort_selected(self, sort_mode: str) -> None:
        descending = sort_mode in {"CPU", "Memory"}
        self._set_process_sort(sort_mode, descending)

    def set_process_detail(self, detail: ProcessDetail) -> None:
        self._current_process_detail_pid = detail.pid
        self.process_detail_label.setText(
            f"PID {detail.pid} {detail.name} | user: {detail.user} | "
            f"status: {detail.status} | threads: {detail.thread_count} | {detail.command_line}"
        )
        self.process_detail_actions.show()

    def clear_process_detail(self) -> None:
        self._current_process_detail_pid = None
        self.process_detail_label.setText("")
        self.process_detail_actions.hide()

    def set_site_profiles(self, sites, secret_lookup=None) -> None:
        self.site_profiles = list(sites)
        self._site_secret_lookup = secret_lookup or getattr(self.controller, "secret_for_site", None)
        self.connection_bar.site_selector.clear()
        self.connection_bar.site_selector.addItem(self._text("site.quick"))
        for site in self.site_profiles:
            self.connection_bar.site_selector.addItem(site.name, site.id)
        if self.site_profiles:
            self.connection_bar.site_selector.setCurrentIndex(1)
            self._populate_connection_fields(self.site_profiles[0])

    def _connect_signals(self) -> None:
        self.connection_bar.connect_button.clicked.connect(self._handle_connect_clicked)
        self.connection_bar.disconnect_button.clicked.connect(self._handle_disconnect_clicked)
        self.connection_bar.site_selector.currentIndexChanged.connect(
            self._handle_site_selection_changed
        )
        self.connection_bar.install_agent_button.clicked.connect(self._handle_install_agent_clicked)
        self.local_panel.path_button.clicked.connect(self._handle_local_path_button_clicked)
        self.remote_panel.path_button.clicked.connect(self._handle_remote_path_button_clicked)
        self.local_panel.path_edit.history_selected.connect(self._handle_local_history_selected)
        self.remote_panel.path_edit.history_selected.connect(self._handle_remote_history_selected)
        self.local_panel.refresh_button.clicked.connect(self._handle_local_refresh_clicked)
        self.remote_panel.refresh_button.clicked.connect(self._handle_remote_refresh_clicked)
        self.local_panel.path_edit.returnPressed.connect(self._handle_local_refresh_clicked)
        self.remote_panel.path_edit.returnPressed.connect(self._handle_remote_refresh_clicked)
        self.local_panel.table.cellDoubleClicked.connect(self._handle_local_double_clicked)
        self.remote_panel.table.cellDoubleClicked.connect(self._handle_remote_double_clicked)
        self.local_panel.table.cellClicked.connect(self._handle_local_clicked)
        self.remote_panel.table.cellClicked.connect(self._handle_remote_clicked)
        self.local_panel.refresh_action.triggered.connect(self._handle_local_refresh_clicked)
        self.remote_panel.refresh_action.triggered.connect(self._handle_remote_refresh_clicked)
        self.local_panel.delete_action.triggered.connect(self._handle_local_delete_action)
        self.remote_panel.delete_action.triggered.connect(self._handle_remote_delete_action)
        self.local_panel.rename_action.triggered.connect(self._handle_local_rename_action)
        self.remote_panel.rename_action.triggered.connect(self._handle_remote_rename_action)
        self.local_panel.copy_path_action.triggered.connect(self._handle_local_copy_path_action)
        self.remote_panel.copy_path_action.triggered.connect(self._handle_remote_copy_path_action)
        self.local_panel.queue_action.triggered.connect(self._handle_local_queue_action)
        self.remote_panel.queue_action.triggered.connect(self._handle_remote_queue_action)
        self.local_panel.transfer_action.triggered.connect(self._handle_upload_clicked)
        self.remote_panel.transfer_action.triggered.connect(self._handle_download_clicked)
        self.local_panel.create_dir_action.triggered.connect(self._handle_local_create_dir_action)
        self.remote_panel.create_dir_action.triggered.connect(self._handle_remote_create_dir_action)
        self.local_panel.create_file_action.triggered.connect(self._handle_local_create_file_action)
        self.remote_panel.create_file_action.triggered.connect(self._handle_remote_create_file_action)
        self.local_panel.action_button.clicked.connect(self._handle_upload_clicked)
        self.remote_panel.action_button.clicked.connect(self._handle_download_clicked)
        self.remote_panel.table.local_paths_dropped.connect(self._handle_remote_drop)
        self.local_panel.table.local_paths_dropped.connect(lambda _paths: self._handle_local_drop())
        self.transfer_concurrency_spin.valueChanged.connect(self._handle_transfer_settings_changed)
        self.transfer_per_server_concurrency_spin.valueChanged.connect(
            self._handle_transfer_settings_changed
        )
        self.transfer_limit_spin.valueChanged.connect(self._handle_transfer_settings_changed)
        self.pause_transfer_button.clicked.connect(self._handle_pause_transfer_clicked)
        self.resume_transfer_button.clicked.connect(self._handle_resume_transfer_clicked)
        self.cancel_transfer_button.clicked.connect(self._handle_cancel_transfer_clicked)
        self.retry_transfer_button.clicked.connect(self._handle_retry_transfer_clicked)
        self.resource_refresh_button.clicked.connect(self._handle_resource_refresh_tick)
        self.resource_install_agent_button.clicked.connect(self._handle_install_agent_clicked)
        self.resource_uninstall_agent_button.clicked.connect(self._handle_uninstall_agent_clicked)
        self.agent_status_card.primary_action_requested.connect(self._handle_install_agent_clicked)
        self.agent_status_card.danger_action_requested.connect(self._handle_uninstall_agent_clicked)
        self.process_detail_button.clicked.connect(self._handle_process_detail_clicked)
        self.process_table.cellDoubleClicked.connect(self._handle_process_cell_double_clicked)
        self.process_table.customContextMenuRequested.connect(self._show_process_context_menu)
        self.process_table.horizontalHeader().sectionClicked.connect(self._handle_process_header_clicked)
        self.process_detail_action.triggered.connect(self._handle_process_detail_clicked)
        self.process_stop_action.triggered.connect(self._handle_process_stop_clicked)
        self.process_restart_action.triggered.connect(self._handle_process_restart_clicked)
        self.process_copy_pid_action.triggered.connect(self._handle_process_copy_pid_clicked)
        self.process_detail_stop_button.clicked.connect(self._handle_process_stop_clicked)
        self.process_detail_restart_button.clicked.connect(self._handle_process_restart_clicked)
        self.process_detail_copy_pid_button.clicked.connect(self._handle_process_copy_pid_clicked)
        self.process_detail_clear_button.clicked.connect(self.clear_process_detail)
        self.disk_partition_selector.currentTextChanged.connect(self._refresh_resource_disk_text)
        self.process_sort_selector.currentTextChanged.connect(self._handle_process_sort_selected)
        self.process_filter_edit.textChanged.connect(self._refresh_process_table)

    def closeEvent(self, event) -> None:
        self.heartbeat_timer.stop()
        self.resource_refresh_timer.stop()
        running_threads = self._running_background_threads()
        for thread in running_threads:
            thread.quit()
            thread.wait(250)
        still_running = [thread for thread in running_threads if thread.isRunning()]
        if still_running:
            self.show_status("Background operation is still running. Close again after it finishes.")
            self.append_log("Close delayed: background operation is still running")
            event.ignore()
            return
        super().closeEvent(event)

    def _running_background_threads(self) -> list[QThread]:
        threads: list[QThread] = []
        active_items = [
            self._active_connection,
            self._active_resource_refresh,
            self._active_remote_directory_load,
        ]
        for active in active_items:
            if active is None:
                continue
            thread = active[0]
            if isinstance(thread, QThread) and thread.isRunning():
                threads.append(thread)
        if self._active_agent_action is not None:
            _label, thread, _worker, _complete = self._active_agent_action
            if isinstance(thread, QThread) and thread.isRunning():
                threads.append(thread)
        for thread, _worker in self._transfer_workers:
            if isinstance(thread, QThread) and thread.isRunning():
                threads.append(thread)
        for thread, _worker, _path in self._remote_operation_workers:
            if isinstance(thread, QThread) and thread.isRunning():
                threads.append(thread)
        if self._active_heartbeat_check is not None:
            thread, _worker = self._active_heartbeat_check
            if isinstance(thread, QThread) and thread.isRunning():
                threads.append(thread)
        return threads

    def _handle_connect_clicked(self) -> None:
        site = self._selected_saved_site()
        secret = self._secret_from_fields()
        remember_secret = True
        if site and secret:
            remember_secret = False
        if not site and secret:
            if self._remember_secret_confirmer is not None:
                remember_secret = self._remember_secret_confirmer(self)
            elif self._should_confirm_remember_secret:
                remember_secret = _confirm_remember_secret(self)
        connect_site = site or self._site_from_fields()
        self._connection_attempt_count += 1
        self.append_log(
            f"Connecting to {connect_site.host}:{connect_site.port} as {connect_site.username}"
        )
        self._set_connection_state("Connecting", "goldenrod")
        self.connection_bar.connect_button.setEnabled(False)
        if hasattr(self.controller, "connect_for_window"):
            self._start_connection(connect_site, secret, remember_secret)
            return
        try:
            self.controller.connect(
                connect_site,
                secret,
                remember_secret=remember_secret,
            )
        except Exception as exc:
            message = classify_connection_error(str(exc))
            self._connection_failure_count += 1
            self._last_connection_error = message
            self.append_log(f"Connection failed: {message}")
            self._set_connection_state("Failed", "red")
            self.heartbeat_timer.stop()
            self.connection_bar.connect_button.setEnabled(True)
            self.show_status(message)
            return
        self._heartbeat_failed_logged = False
        self._last_connection_error = None
        self._set_connection_state("Connected", "green")
        self.heartbeat_timer.start()
        self.resource_refresh_timer.start()
        self._handle_resource_refresh_tick()
        self.connection_bar.connect_button.setEnabled(True)

    def _start_connection(
        self,
        connect_site: SiteProfile,
        secret: str | None,
        remember_secret: bool,
    ) -> None:
        if self._connection_running:
            self.append_log("Connection already in progress")
            return
        self._connection_running = True
        thread = QThread(self)
        worker = ResourceRefreshWorker(
            lambda: self.controller.connect_for_window(
                connect_site,
                secret,
                remember_secret=remember_secret,
            )
        )
        worker.moveToThread(thread)
        self._active_connection = (thread, worker)
        self._connection_workers.append((thread, worker))
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._finish_connection, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(self._fail_connection, Qt.ConnectionType.QueuedConnection)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    @Slot(object)
    def _finish_connection(self, result) -> None:
        self._publish_connection_result(result)
        self._heartbeat_failed_logged = False
        self._last_connection_error = None
        self._set_connection_state("Connected", "green")
        if self._connection_test_running and self.getting_started_dialog is not None:
            self.getting_started_dialog.set_status(self._text("getting_started.connection_ok"))
            self.getting_started_dialog.set_connection_ready(True)
            self.append_log("Connection test passed")
        self.heartbeat_timer.start()
        self.resource_refresh_timer.start()
        if not isinstance(result, dict) or result.get("resource_snapshot") is None:
            self._handle_resource_refresh_tick()
        self.connection_bar.connect_button.setEnabled(True)
        self._connection_test_running = False
        self._cleanup_connection_worker()

    @Slot(str)
    def _fail_connection(self, error: str) -> None:
        message = classify_connection_error(error)
        self._connection_failure_count += 1
        self._last_connection_error = message
        self._append_background_failure("connection", message)
        self.append_log(f"Connection failed: {message}")
        if self._connection_test_running and self.getting_started_dialog is not None:
            self.getting_started_dialog.set_status(message)
            self.getting_started_dialog.set_connection_ready(False)
            self.append_log(f"Connection test failed: {message}")
        self._set_connection_state("Failed", "red")
        self.heartbeat_timer.stop()
        self.resource_refresh_timer.stop()
        self.connection_bar.connect_button.setEnabled(True)
        self.show_status(message)
        self._connection_test_running = False
        self._cleanup_connection_worker()

    def _publish_connection_result(self, result) -> None:
        if not isinstance(result, dict):
            return
        self.set_remote_entries(result["entries"], result["remote_path"])
        self.set_monitoring_status(result["monitoring_status"])
        if result.get("agent_version"):
            self.set_agent_version(result.get("agent_version"))
        for status in result.get("agent_status_sequence", []):
            self.set_agent_status(
                status,
                version=result.get("agent_version") if status is True else None,
            )
        agent_status = result.get("agent_status")
        if agent_status is not None and not result.get("agent_status_sequence"):
            self.set_agent_status(
                agent_status,
                version=result.get("agent_version") if agent_status is True else None,
            )
        for message in result.get("logs", []):
            self.append_log(message)
        snapshot = result.get("resource_snapshot")
        if snapshot is not None:
            self.set_resource_snapshot(snapshot)
        status = result.get("agent_status_message") or result.get("status")
        if status:
            self.show_status(status)

    def _cleanup_connection_worker(self) -> None:
        self._connection_running = False
        if self._active_connection is None:
            return
        thread, worker = self._active_connection
        self._active_connection = None
        try:
            self._connection_workers.remove((thread, worker))
        except ValueError:
            pass
        thread.quit()
        thread.wait(1000)

    def _handle_disconnect_clicked(self) -> None:
        self.append_log("Disconnect requested")
        self._set_connection_state("Disconnecting", "goldenrod")
        self.connection_bar.disconnect_button.setEnabled(False)
        log_checkpoint = self.log_view.toPlainText()
        try:
            self.controller.disconnect()
        except Exception as exc:
            self.append_log(f"Disconnect failed: {exc}")
            self._set_connection_state(f"Disconnect failed: {exc}", "red")
            self.show_status(str(exc))
            return
        finally:
            self.connection_bar.disconnect_button.setEnabled(True)
        self.heartbeat_timer.stop()
        self.resource_refresh_timer.stop()
        self._heartbeat_failed_logged = False
        self._set_connection_state("Disconnected", "grey")
        if "Disconnected" not in self.log_view.toPlainText()[len(log_checkpoint) :]:
            self.append_log("Disconnected")

    def _handle_new_session_clicked(self) -> None:
        factory = self._new_session_factory or MainWindow
        window = factory()
        self._session_windows.append(window)
        if hasattr(window, "show"):
            window.show()

    def _handle_install_agent_clicked(self) -> None:
        label = "update" if self._agent_installed is True else "install"
        self.append_log(f"Agent {label} requested")
        if not self._confirm_agent_action(label):
            self.append_log(f"Agent {label} canceled")
            return
        self.append_log(f"Agent {label} confirmed")
        self._start_agent_action(
            label=label,
            action=self._run_agent_install,
            complete=self._complete_agent_install,
        )

    def _handle_uninstall_agent_clicked(self) -> None:
        self.append_log("Agent uninstall requested")
        if not self._agent_install_confirmer(self):
            self.append_log("Agent uninstall canceled")
            return
        self.append_log("Agent uninstall confirmed")
        self._start_agent_action(
            label="uninstall",
            action=self._run_agent_uninstall,
            complete=self._complete_agent_uninstall,
        )

    def _start_agent_action(
        self,
        *,
        label: str,
        action: Callable[[Callable[[str], None]], object],
        complete: Callable[[object], None],
    ) -> None:
        if self._active_agent_action is not None:
            self.append_log(f"Agent {label} request ignored: another Agent action is running")
            return
        self._set_agent_action_enabled(False)
        operation = "uninstalling" if label == "uninstall" else "installing"
        self.set_agent_status_model(
            view_model_for_agent(
                self._agent_installed,
                version=self._agent_version,
                current_version=__version__,
                operation=operation,
            )
        )
        self.agent_status_card.clear_operation_steps()
        thread = QThread(self)
        worker = AgentActionWorker(action)
        worker.moveToThread(thread)
        self._active_agent_action = (label, thread, worker, complete)
        self._agent_workers.append((thread, worker))
        thread.started.connect(worker.run)
        worker.progress.connect(self._handle_agent_progress, Qt.ConnectionType.QueuedConnection)
        worker.succeeded.connect(self._finish_agent_action, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(self._fail_agent_action, Qt.ConnectionType.QueuedConnection)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    @Slot(str)
    def _handle_agent_progress(self, message: str) -> None:
        self.append_log(message)
        self.agent_status_card.add_operation_step(message)

    def _run_agent_install(self, progress: Callable[[str], None]):
        return self.controller.install_agent_with_progress(progress)

    def _run_agent_uninstall(self, progress: Callable[[str], None]):
        return self.controller.uninstall_agent_with_progress(progress)

    def _complete_agent_install(self, result) -> None:
        if hasattr(self.controller, "complete_agent_install") and result is not None:
            self.controller.complete_agent_install(result)

    def _complete_agent_uninstall(self, result) -> None:
        if hasattr(self.controller, "complete_agent_uninstall") and result is not None:
            self.controller.complete_agent_uninstall(result)

    @Slot(object)
    def _finish_agent_action(self, result) -> None:
        if self._active_agent_action is None:
            return
        label, _thread, _worker, complete = self._active_agent_action
        try:
            complete(result)
        except Exception as exc:
            self.append_log(f"Agent {label} completion failed: {exc}")
            self.show_status(str(exc))
        message = f"Agent {label} command finished"
        self.append_log(message)
        self.agent_status_card.set_operation_result(message)
        if label in {"install", "update"}:
            self._handle_resource_refresh_tick()
        self._set_agent_action_enabled(True)
        self._cleanup_agent_worker()

    @Slot(str)
    def _fail_agent_action(self, error: str) -> None:
        label = self._active_agent_action[0] if self._active_agent_action else "install"
        classified_error = classify_agent_error(error)
        self._append_background_failure(f"agent {label}", classified_error)
        if label == "install":
            message = f"Agent installation failed: {classified_error}"
        elif label == "update":
            message = f"Agent update failed: {classified_error}"
        else:
            message = f"Agent uninstall failed: {classified_error}"
        self.append_log(message)
        self.agent_status_card.set_operation_result(message)
        self.show_status(message)
        self._set_agent_action_enabled(True)
        self._cleanup_agent_worker()

    def _cleanup_agent_worker(self) -> None:
        if self._active_agent_action is None:
            return
        _label, thread, worker, _complete = self._active_agent_action
        self._active_agent_action = None
        try:
            self._agent_workers.remove((thread, worker))
        except ValueError:
            pass
        thread.quit()
        thread.wait(1000)

    def _set_agent_action_enabled(self, enabled: bool) -> None:
        self.connection_bar.install_agent_button.setEnabled(enabled)
        self.resource_install_agent_button.setEnabled(enabled)
        self.resource_uninstall_agent_button.setEnabled(enabled)

    def _refresh_agent_action_text(self) -> None:
        if not hasattr(self, "connection_bar"):
            return
        key = (
            "connection.update_agent"
            if self._agent_installed is True
            else "connection.install_agent"
        )
        self.connection_bar.install_agent_button.setText(self._text(key))

    def _confirm_agent_action(self, label: str) -> bool:
        try:
            return self._agent_install_confirmer(self, label)
        except TypeError:
            return self._agent_install_confirmer(self)

    def _handle_local_refresh_clicked(self) -> None:
        self.local_panel.clear_selection()
        path_text = self.local_panel.path_edit.text().strip()
        path = Path(path_text) if path_text else Path.home()
        self._load_local_directory(path)

    def _handle_remote_refresh_clicked(self) -> None:
        self.remote_panel.clear_selection()
        remote_path = self._remote_path_from_field()
        self._load_remote_directory(remote_path, force_refresh=True)

    def _handle_local_history_selected(self, path_text: str) -> None:
        self.local_panel.clear_selection()
        self._load_local_directory(Path(path_text))

    def _handle_remote_history_selected(self, path_text: str) -> None:
        self.remote_panel.clear_selection()
        self._load_remote_directory(PurePosixPath(path_text))

    def _handle_local_path_button_clicked(self) -> None:
        current = self.local_panel.path_edit.text().strip() or str(Path.home())
        selected = self._local_directory_chooser(self, current)
        if not selected:
            return
        path = Path(selected)
        self.local_panel.path_edit.setText(str(path))
        self.local_panel.clear_selection()
        self._load_local_directory(path)

    def _handle_remote_path_button_clicked(self) -> None:
        remote_name = self.remote_panel.selected_name()
        if not remote_name or not self.remote_panel.selected_is_dir():
            self.show_status("Select a remote directory to open")
            return
        self.remote_panel.clear_selection()
        self._load_remote_directory(self._remote_path_from_field() / remote_name)

    def _handle_local_double_clicked(self, row: int, _column: int) -> None:
        if self.local_panel.is_parent_at(row):
            self._load_local_directory(self._local_parent())
            return
        if not self.local_panel.is_dir_at(row):
            return
        name = self.local_panel.name_at(row)
        if name:
            self._load_local_directory(self._local_root() / name)

    def _handle_remote_double_clicked(self, row: int, _column: int) -> None:
        if self.remote_panel.is_parent_at(row):
            self._load_remote_directory(self._remote_parent())
            return
        if not self.remote_panel.is_dir_at(row):
            return
        name = self.remote_panel.name_at(row)
        if name:
            self._load_remote_directory(self._remote_path_from_field() / name)

    def _handle_local_clicked(self, row: int, _column: int) -> None:
        if self.local_panel.is_parent_at(row):
            self._load_local_directory(self._local_parent())

    def _handle_remote_clicked(self, row: int, _column: int) -> None:
        if self.remote_panel.is_parent_at(row):
            self._load_remote_directory(self._remote_parent())

    def _load_local_directory(self, path: Path) -> None:
        self.local_panel.path_edit.add_history(str(path))
        self.controller.load_local_directory(path)

    def _load_remote_directory(self, path: PurePosixPath, *, force_refresh: bool = False) -> None:
        if self._remote_directory_loading:
            self.show_status("Remote directory load already in progress")
            return
        self.remote_panel.path_edit.add_history(str(path))
        self._set_remote_loading(True, path)
        if not hasattr(self.controller, "load_remote_directory"):
            try:
                self._list_remote_directory_from_controller(path, force_refresh)
            finally:
                self._set_remote_loading(False, path)
            return
        self._remote_directory_loading = True
        thread = QThread(self)
        worker = RemoteDirectoryWorker(lambda: self._load_remote_directory_from_controller(path, force_refresh))
        worker.moveToThread(thread)
        self._active_remote_directory_load = (thread, worker, path)
        self._remote_directory_workers.append((thread, worker, path))
        thread.started.connect(worker.run)
        worker.succeeded.connect(
            self._finish_remote_directory_load,
            Qt.ConnectionType.QueuedConnection,
        )
        worker.failed.connect(
            self._fail_remote_directory_load,
            Qt.ConnectionType.QueuedConnection,
        )
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _load_remote_directory_from_controller(self, path: PurePosixPath, force_refresh: bool):
        try:
            return self.controller.load_remote_directory(path, force_refresh=force_refresh)
        except TypeError as exc:
            if "force_refresh" not in str(exc):
                raise
            return self.controller.load_remote_directory(path)

    def _list_remote_directory_from_controller(self, path: PurePosixPath, force_refresh: bool) -> None:
        try:
            self.controller.list_remote_directory(path, force_refresh=force_refresh)
        except TypeError as exc:
            if "force_refresh" not in str(exc):
                raise
            self.controller.list_remote_directory(path)

    def _set_remote_loading(self, loading: bool, path: PurePosixPath) -> None:
        enabled = not loading
        self.remote_panel.table.setEnabled(enabled)
        self.remote_panel.refresh_button.setEnabled(enabled)
        self.remote_panel.path_button.setEnabled(enabled)
        self.remote_panel.action_button.setEnabled(enabled)
        if loading:
            self.remote_panel.refresh_button.setProperty("buttonRole", "loading")
            self.show_status(self._text("status.loading_remote", path=path))
        else:
            self.remote_panel.refresh_button.setProperty("buttonRole", "neutral")

    @Slot(object)
    def _finish_remote_directory_load(self, result) -> None:
        entries, loaded_path, status = result
        self.set_remote_entries(entries, loaded_path)
        if status:
            self.show_status(status)
            self.append_log(status)
        self._set_remote_loading(False, loaded_path)
        self._cleanup_remote_directory_worker()

    @Slot(str)
    def _fail_remote_directory_load(self, error: str) -> None:
        self._append_background_failure("remote directory", error)
        message = f"Remote directory load failed: {error}"
        self.show_status(message)
        self.append_log(message)
        path = self._active_remote_directory_load[2] if self._active_remote_directory_load else PurePosixPath(".")
        self._set_remote_loading(False, path)
        self._cleanup_remote_directory_worker()

    def _cleanup_remote_directory_worker(self) -> None:
        self._remote_directory_loading = False
        if self._active_remote_directory_load is None:
            return
        thread, worker, path = self._active_remote_directory_load
        self._active_remote_directory_load = None
        try:
            self._remote_directory_workers.remove((thread, worker, path))
        except ValueError:
            pass
        thread.quit()
        thread.wait(1000)

    def _start_remote_operation(
        self,
        label: str,
        action: Callable[[], None],
        refresh_path: PurePosixPath | None,
    ) -> None:
        self.append_log(f"Remote operation started: {label}")
        self.show_status(f"Remote operation started: {label}")
        thread = QThread(self)
        worker = TransferOperationWorker(label, action)
        worker.moveToThread(thread)
        self._remote_operation_workers.append((thread, worker, refresh_path))
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._finish_remote_operation, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(self._fail_remote_operation, Qt.ConnectionType.QueuedConnection)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    @Slot(str)
    def _finish_remote_operation(self, label: str) -> None:
        thread = self.sender().thread() if self.sender() is not None else None
        refresh_path = self._remote_operation_refresh_path(thread)
        message = f"Remote operation finished: {label}"
        self.show_status(message)
        self.append_log(message)
        self._cleanup_remote_operation_worker(thread)
        if refresh_path is not None:
            self._load_remote_directory(refresh_path, force_refresh=True)

    @Slot(str)
    def _fail_remote_operation(self, error: str) -> None:
        thread = self.sender().thread() if self.sender() is not None else None
        self._append_background_failure("remote operation", error)
        message = f"Remote operation failed: {error}"
        self.show_status(message)
        self.append_log(message)
        self._cleanup_remote_operation_worker(thread)

    def _remote_operation_refresh_path(self, thread: QThread | None) -> PurePosixPath | None:
        for active_thread, _worker, refresh_path in self._remote_operation_workers:
            if active_thread is thread:
                return refresh_path
        return None

    def _cleanup_remote_operation_worker(self, thread: QThread | None) -> None:
        remaining = []
        for active_thread, worker, refresh_path in self._remote_operation_workers:
            if active_thread is thread:
                active_thread.quit()
                active_thread.wait(1000)
            else:
                remaining.append((active_thread, worker, refresh_path))
        self._remote_operation_workers = remaining

    def _handle_upload_clicked(self) -> None:
        local_root = Path(self.local_panel.path_edit.text().strip() or Path.home())
        for local_name in self.local_panel.selected_names():
            local_path = local_root / local_name
            policy = self._conflict_policy_for_name(self.remote_panel, local_name)
            if policy is None:
                continue
            remote_path = self._remote_path_from_field() / local_name
            self._append_transfer_preview(local_path, remote_path, Direction.UPLOAD)
            self._start_transfer_operation(
                f"upload {local_name}",
                lambda local_path=local_path, remote_path=remote_path, policy=policy: self.controller.upload_file(
                    local_path,
                    remote_path,
                    conflict_policy=policy,
                ),
            )

    def _handle_download_clicked(self) -> None:
        local_root = Path(self.local_panel.path_edit.text().strip() or Path.home())
        for remote_name in self.remote_panel.selected_names():
            remote_path = self._remote_path_from_field() / remote_name
            local_path = local_root / remote_name
            policy = self._local_conflict_policy(local_path)
            if policy is None:
                continue
            self._append_transfer_preview(remote_path, local_path, Direction.DOWNLOAD)
            self._start_transfer_operation(
                f"download {remote_name}",
                lambda remote_path=remote_path, local_path=local_path, policy=policy: self.controller.download_file(
                    remote_path,
                    local_path,
                    conflict_policy=policy,
                ),
            )

    def _start_transfer_operation(self, label: str, action: Callable[[], None]) -> None:
        thread = QThread(self)
        worker = TransferOperationWorker(label, action)
        worker.moveToThread(thread)
        self._transfer_workers.append((thread, worker))
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._finish_transfer_operation, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(self._fail_transfer_operation, Qt.ConnectionType.QueuedConnection)
        worker.succeeded.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(
            lambda thread=thread, worker=worker: self._discard_transfer_worker(thread, worker)
        )
        thread.finished.connect(worker.deleteLater)
        thread.start()

    @Slot(str)
    def _finish_transfer_operation(self, label: str) -> None:
        self.append_log(f"Transfer {label} finished", category="transfer")
        self._cleanup_finished_transfer_workers()

    @Slot(str)
    def _fail_transfer_operation(self, error: str) -> None:
        self.append_log(f"Transfer failed: {error}", category="error", level="error")
        self.show_status(f"Transfer failed: {error}")
        self._cleanup_finished_transfer_workers()

    def _cleanup_finished_transfer_workers(self) -> None:
        remaining = []
        for thread, worker in self._transfer_workers:
            try:
                is_running = thread.isRunning()
            except RuntimeError:
                continue
            if is_running:
                remaining.append((thread, worker))
                continue
            thread.quit()
            thread.wait(1000)
        self._transfer_workers = remaining

    def _discard_transfer_worker(self, thread: QThread, worker: TransferOperationWorker) -> None:
        self._transfer_workers = [
            (active_thread, active_worker)
            for active_thread, active_worker in self._transfer_workers
            if not (active_thread is thread and active_worker is worker)
        ]

    def _append_transfer_preview(
        self,
        source_path: Path | PurePosixPath,
        destination_path: Path | PurePosixPath,
        direction: Direction,
    ) -> None:
        size = self._transfer_preview_size(source_path, direction)
        task_id = f"ui-{direction.value}-{len(self._optimistic_transfer_items) + 1}"
        item = TransferItem(
            id=f"{task_id}-item",
            task_id=task_id,
            server_id=self._site_from_fields().id,
            direction=direction,
            source_path=source_path,
            destination_path=destination_path,
            temporary_path=destination_path.with_name(f".filezall.{destination_path.name}.part"),
            size_bytes=size,
            protocol=_protocol_from_label(self.connection_bar.protocol_selector.currentText()),
            bytes_transferred=0,
            status=TransferStatus.PENDING,
        )
        self.set_transfer_items([*self._optimistic_transfer_items, item])

    def _transfer_preview_size(self, source_path: Path | PurePosixPath, direction: Direction) -> int:
        if direction is Direction.UPLOAD and isinstance(source_path, Path) and source_path.is_file():
            return source_path.stat().st_size
        panel = self.remote_panel if direction is Direction.DOWNLOAD else self.local_panel
        selected_rows = [row for row in panel.selected_rows() if not panel.is_parent_at(row)]
        if not selected_rows:
            return 0
        size_item = panel.table.item(selected_rows[0], 1)
        if size_item is None:
            return 0
        try:
            return int(size_item.text())
        except ValueError:
            return 0

    def _conflict_policy_for_name(self, panel, destination_name: str) -> ConflictPolicy | None:
        if not self._panel_has_entry_named(panel, destination_name):
            return ConflictPolicy.OVERWRITE
        decision = self._conflict_policy_prompt(self, destination_name)
        return decision.policy if decision is not None else None

    def _local_conflict_policy(self, destination_path: Path) -> ConflictPolicy | None:
        if not destination_path.exists():
            return ConflictPolicy.OVERWRITE
        decision = self._conflict_policy_prompt(self, destination_path.name)
        return decision.policy if decision is not None else None

    @staticmethod
    def _panel_has_entry_named(panel, name: str) -> bool:
        for row in range(panel.table.rowCount()):
            if panel.is_parent_at(row):
                continue
            if panel.name_at(row) == name:
                return True
        return False

    def _handle_local_queue_action(self) -> None:
        for local_name in self.local_panel.selected_names():
            self.controller.add_to_queue(
                self._local_root() / local_name,
                self._remote_path_from_field() / local_name,
                Direction.UPLOAD,
            )

    def _handle_remote_queue_action(self) -> None:
        for remote_name in self.remote_panel.selected_names():
            self.controller.add_to_queue(
                self._remote_path_from_field() / remote_name,
                self._local_root() / remote_name,
                Direction.DOWNLOAD,
            )

    def _handle_transfer_settings_changed(self) -> None:
        limit = self.transfer_limit_spin.value()
        self.apply_transfer_settings(
            TransferSettings(
                max_concurrent=self.transfer_concurrency_spin.value(),
                max_concurrent_per_server=self.transfer_per_server_concurrency_spin.value(),
                bytes_per_second_limit=limit * 1024 if limit > 0 else None,
            )
        )

    def apply_transfer_settings(self, settings: TransferSettings) -> None:
        self.transfer_settings = settings
        self.transfer_concurrency_spin.blockSignals(True)
        self.transfer_per_server_concurrency_spin.blockSignals(True)
        self.transfer_limit_spin.blockSignals(True)
        self.transfer_concurrency_spin.setValue(settings.max_concurrent)
        self.transfer_per_server_concurrency_spin.setValue(
            settings.max_concurrent_per_server or settings.max_concurrent
        )
        self.transfer_limit_spin.setValue(
            int(settings.bytes_per_second_limit / 1024)
            if settings.bytes_per_second_limit
            else 0
        )
        self.transfer_concurrency_spin.blockSignals(False)
        self.transfer_per_server_concurrency_spin.blockSignals(False)
        self.transfer_limit_spin.blockSignals(False)
        if hasattr(self.controller, "set_transfer_settings"):
            self.controller.set_transfer_settings(settings)

    def _handle_remote_drop(self, local_paths) -> None:
        for local_path in [Path(path) for path in local_paths]:
            if not local_path.exists():
                continue
            self.controller.add_to_queue(
                local_path,
                self._remote_path_from_field() / local_path.name,
                Direction.UPLOAD,
            )

    def _handle_local_drop(self) -> None:
        for remote_name in self.remote_panel.selected_names():
            self.controller.add_to_queue(
                self._remote_path_from_field() / remote_name,
                self._local_root() / remote_name,
                Direction.DOWNLOAD,
            )

    def _handle_local_delete_action(self) -> None:
        entries = self._selected_panel_entries(self.local_panel)
        if not entries or not self._delete_confirmer(self, [name for name, _is_dir in entries], False):
            return
        for local_name, is_dir in entries:
            self.controller.delete_path(self._local_root() / local_name, remote=False, is_dir=is_dir)

    def _handle_remote_delete_action(self) -> None:
        entries = self._selected_panel_entries(self.remote_panel)
        if not entries or not self._delete_confirmer(self, [name for name, _is_dir in entries], True):
            return
        remote_root = self._remote_path_from_field()

        def delete_entries() -> None:
            for remote_name, is_dir in entries:
                self.controller.delete_path(
                    remote_root / remote_name,
                    remote=True,
                    is_dir=is_dir,
                )

        self._start_remote_operation(
            f"delete {len(entries)} item(s)",
            delete_entries,
            refresh_path=remote_root,
        )

    def _selected_panel_entries(self, panel) -> list[tuple[str, bool]]:
        entries = []
        for row in panel.selected_rows():
            if panel.is_parent_at(row):
                continue
            name = panel.name_at(row)
            if name:
                entries.append((name, panel.is_dir_at(row)))
        return entries

    def _handle_local_rename_action(self) -> None:
        name = self.local_panel.selected_name()
        if not name:
            return
        new_name = self._rename_prompt(self, name)
        if not new_name:
            return
        source = self._local_root() / name
        self.controller.rename_path(source, source.with_name(new_name), remote=False)

    def _handle_remote_rename_action(self) -> None:
        name = self.remote_panel.selected_name()
        if not name:
            return
        new_name = self._rename_prompt(self, name)
        if not new_name:
            return
        remote_root = self._remote_path_from_field()
        source = remote_root / name
        self._start_remote_operation(
            f"rename {name}",
            lambda: self.controller.rename_path(source, source.parent / new_name, remote=True),
            refresh_path=remote_root,
        )

    def _handle_local_copy_path_action(self) -> None:
        paths = [str(self._local_root() / name) for name in self.local_panel.selected_names()]
        self._copy_paths(paths)

    def _handle_remote_copy_path_action(self) -> None:
        paths = [str(self._remote_path_from_field() / name) for name in self.remote_panel.selected_names()]
        self._copy_paths(paths)

    def _copy_paths(self, paths: list[str]) -> None:
        if not paths:
            return
        text = "\n".join(paths)
        self.last_copied_text = text
        QApplication.clipboard().setText(text)
        self.show_status(f"Copied {len(paths)} path(s)")
        self.append_log(f"Copied {len(paths)} path(s)")

    def _handle_local_create_dir_action(self) -> None:
        self.controller.create_directory(self._local_root(), remote=False)

    def _handle_remote_create_dir_action(self) -> None:
        remote_root = self._remote_path_from_field()
        self._start_remote_operation(
            "create directory",
            lambda: self.controller.create_directory(remote_root, remote=True),
            refresh_path=remote_root,
        )

    def _handle_local_create_file_action(self) -> None:
        self.controller.create_file(self._local_root(), remote=False)

    def _handle_remote_create_file_action(self) -> None:
        remote_root = self._remote_path_from_field()
        self._start_remote_operation(
            "create file",
            lambda: self.controller.create_file(remote_root, remote=True),
            refresh_path=remote_root,
        )

    def _handle_pause_transfer_clicked(self) -> None:
        if task_id := self._selected_transfer_task_id():
            self.controller.pause_transfer(task_id)

    def _handle_resume_transfer_clicked(self) -> None:
        if task_id := self._selected_transfer_task_id():
            self.controller.resume_transfer(task_id)

    def _handle_cancel_transfer_clicked(self) -> None:
        if task_id := self._selected_transfer_task_id():
            self.controller.cancel_transfer(task_id)

    def _handle_retry_transfer_clicked(self) -> None:
        if task_id := self._selected_transfer_task_id():
            self.controller.retry_transfer(task_id)

    def _handle_process_detail_clicked(self) -> None:
        if pid := self._active_process_id():
            self.controller.show_process_detail(pid)

    def _handle_process_cell_double_clicked(self, row: int, _column: int) -> None:
        self.process_table.selectRow(row)
        self._handle_process_detail_clicked()

    def _show_process_context_menu(self, position) -> None:
        row = self.process_table.indexAt(position).row()
        if row >= 0:
            self.process_table.selectRow(row)
        self.process_menu.exec(self.process_table.viewport().mapToGlobal(position))

    def _handle_process_stop_clicked(self) -> None:
        if pid := self._active_process_id():
            try:
                self.controller.stop_process(pid)
            except Exception as exc:
                self.show_status(str(exc))
                self.append_log(f"Stop process failed: {exc}", category="error", level="error")
                return
            self.append_log(f"Stop process requested: {pid}", category="resource")

    def _handle_process_restart_clicked(self) -> None:
        if pid := self._active_process_id():
            try:
                self.controller.restart_process(pid)
            except Exception as exc:
                self.show_status(str(exc))
                self.append_log(f"Restart process failed: {exc}", category="error", level="error")
                return
            self.append_log(f"Restart process requested: {pid}", category="resource")

    def _handle_process_copy_pid_clicked(self) -> None:
        if pid := self._active_process_id():
            text = str(pid)
            self.last_copied_text = text
            QApplication.clipboard().setText(text)
            self.show_status(f"Copied process ID {text}")
            self.append_log(f"Copied process ID {text}", category="resource")

    def _handle_resource_refresh_tick(self) -> None:
        if self._resource_refresh_running:
            return
        if not hasattr(self.controller, "load_resource_snapshot"):
            self.controller.refresh_resources()
            self.show_status("Resource snapshot refreshed")
            self.append_log("Resource snapshot refreshed")
            return
        self._resource_refresh_running = True
        thread = QThread(self)
        worker = ResourceRefreshWorker(self._resource_refresh_action)
        worker.moveToThread(thread)
        self._active_resource_refresh = (thread, worker)
        self._resource_refresh_workers.append((thread, worker))
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._finish_resource_refresh, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(self._fail_resource_refresh, Qt.ConnectionType.QueuedConnection)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _resource_refresh_action(self):
        if hasattr(self.controller, "load_resource_snapshot"):
            return self.controller.load_resource_snapshot()
        self.controller.refresh_resources()
        return None, "Resource snapshot refreshed"

    @Slot(object)
    def _finish_resource_refresh(self, result) -> None:
        if isinstance(result, tuple) and len(result) == 2:
            snapshot, status = result
            if snapshot is not None:
                self.set_resource_snapshot(snapshot)
            if status:
                self.show_status(status)
                self.append_log(status)
        self._cleanup_resource_refresh()

    @Slot(str)
    def _fail_resource_refresh(self, error: str) -> None:
        self._append_background_failure("resource refresh", error)
        message = f"Resource refresh failed: {error}"
        self.show_status(message)
        self.append_log(message)
        self._cleanup_resource_refresh()

    def _cleanup_resource_refresh(self) -> None:
        self._resource_refresh_running = False
        if self._active_resource_refresh is None:
            return
        thread, worker = self._active_resource_refresh
        self._active_resource_refresh = None
        try:
            self._resource_refresh_workers.remove((thread, worker))
        except ValueError:
            pass
        thread.quit()
        thread.wait(1000)

    def _handle_heartbeat_tick(self) -> None:
        if self._heartbeat_running:
            return
        self._blink_connection_state("goldenrod")
        self._heartbeat_running = True
        thread = QThread(self)
        worker = ResourceRefreshWorker(lambda: self.controller.heartbeat())
        worker.moveToThread(thread)
        self._active_heartbeat_check = (thread, worker)
        self._heartbeat_workers.append((thread, worker))
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._finish_heartbeat_check, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(self._fail_heartbeat_check, Qt.ConnectionType.QueuedConnection)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    @Slot(object)
    def _finish_heartbeat_check(self, ok) -> None:
        try:
            if ok:
                self._heartbeat_failed_logged = False
                self._connection_recovery.record_success()
                self._set_connection_state("Connected", "green")
            else:
                self._log_heartbeat_failure("Heartbeat failed: disconnected")
                self._set_connection_state("Disconnected", "red")
        finally:
            self._cleanup_heartbeat_worker()

    @Slot(str)
    def _fail_heartbeat_check(self, error: str) -> None:
        try:
            self._log_heartbeat_failure(f"Heartbeat failed: {error}")
            self._set_connection_state(f"Disconnected: {error}", "red")
        finally:
            self._cleanup_heartbeat_worker()

    def _cleanup_heartbeat_worker(self) -> None:
        self._heartbeat_running = False
        if self._active_heartbeat_check is None:
            return
        thread, worker = self._active_heartbeat_check
        self._active_heartbeat_check = None
        try:
            self._heartbeat_workers.remove((thread, worker))
        except ValueError:
            pass
        thread.quit()
        thread.wait(1000)

    def _log_heartbeat_failure(self, message: str) -> None:
        self._heartbeat_failure_count += 1
        self._last_heartbeat_error = message
        self._connection_recovery.record_failure(message, now=self.connection_recovery_clock())
        if self._heartbeat_failed_logged:
            return
        self.append_log(message)
        self._heartbeat_failed_logged = True

    def _append_background_failure(self, operation: str, error: str) -> None:
        self.append_log(f"Background operation failed [{operation}]: {error}")

    def _set_connection_state(self, text: str, color: str) -> None:
        self.connection_state_label.setText("")
        self.connection_state_label.setToolTip(text)
        self.connection_state_label.setProperty("connectionState", _connection_state_key(text))
        self.connection_state_label.setStyleSheet(
            "border-radius: 6px; "
            f"background-color: {color}; "
            f"border: 1px solid {color};"
        )

    def _blink_connection_state(self, color: str) -> None:
        count = int(self.connection_state_label.property("blinkCount") or 0) + 1
        self.connection_state_label.setProperty("lastBlinkColor", color)
        self.connection_state_label.setProperty("blinkCount", count)
        self._set_connection_state("Checking", color)
        QApplication.processEvents()

    def _handle_site_selection_changed(self, index: int) -> None:
        if index <= 0:
            return
        site_index = index - 1
        if site_index < len(self.site_profiles):
            self._populate_connection_fields(self.site_profiles[site_index])

    def _populate_connection_fields(self, site: SiteProfile) -> None:
        self.connection_bar.host_edit.setText(site.host)
        self.connection_bar.port_edit.setText(str(site.port))
        self.connection_bar.username_edit.setText(site.username)
        self.connection_bar.protocol_selector.setCurrentText(site.protocol.name)
        auth_data = "ssh_key" if site.auth_mode == AuthMode.SSH_KEY else "password"
        self.connection_bar.auth_mode_selector.setCurrentIndex(
            max(self.connection_bar.auth_mode_selector.findData(auth_data), 0)
        )
        self.connection_bar.ssh_key_path_edit.setText(str(site.ssh_key_path or ""))
        self.local_panel.path_edit.setText(str(site.default_local_path or ""))
        self.remote_panel.path_edit.setText(str(site.default_remote_path))
        self.connection_bar.secret_edit.clear()

    def _site_from_fields(self) -> SiteProfile:
        host = self.connection_bar.host_edit.text().strip()
        username = self.connection_bar.username_edit.text().strip()
        auth_mode = (
            AuthMode.SSH_KEY
            if self.connection_bar.auth_mode_selector.currentData() == "ssh_key"
            else AuthMode.PASSWORD
        )
        ssh_key_text = self.connection_bar.ssh_key_path_edit.text().strip()
        remote_path = self.remote_panel.path_edit.text().strip() or "~"
        local_path = self.local_panel.path_edit.text().strip()
        return SiteProfile(
            id=f"{host}:{self.connection_bar.port_edit.text().strip()}:{username}",
            name=host or "Quick Connect",
            host=host,
            port=int(self.connection_bar.port_edit.text().strip() or "22"),
            protocol=_protocol_from_label(self.connection_bar.protocol_selector.currentText()),
            username=username,
            auth_mode=auth_mode,
            default_remote_path=PurePosixPath(remote_path),
            default_local_path=Path(local_path) if local_path else None,
            ssh_key_path=Path(ssh_key_text) if ssh_key_text else None,
        )

    def _selected_saved_site(self) -> SiteProfile | None:
        index = self.connection_bar.site_selector.currentIndex()
        if index <= 0:
            return None
        site_index = index - 1
        if site_index >= len(self.site_profiles):
            return None
        return self.site_profiles[site_index]

    def _secret_from_fields(self) -> str | None:
        secret = self.connection_bar.secret_edit.text()
        return secret if secret else None

    def _remote_path_from_field(self) -> PurePosixPath:
        return PurePosixPath(self.remote_panel.path_edit.text().strip() or "~")

    def _local_root(self) -> Path:
        return Path(self.local_panel.path_edit.text().strip() or Path.home())

    def _local_parent(self) -> Path:
        current = self._local_root()
        return current.parent if current.parent != current else current

    def _remote_parent(self) -> PurePosixPath:
        current = self._remote_path_from_field()
        if str(current) in {"", ".", "~", "/"}:
            return current
        return current.parent

    def _selected_transfer_task_id(self) -> str | None:
        selected = self.transfer_table.selectionModel().selectedRows()
        if not selected:
            return None
        item = self.transfer_table.item(selected[0].row(), 0)
        return str(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def _selected_process_id(self) -> int | None:
        selected = self.process_table.selectionModel().selectedRows()
        if not selected:
            return None
        item = self.process_table.item(selected[0].row(), 0)
        return int(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def _active_process_id(self) -> int | None:
        return self._selected_process_id() or self._current_process_detail_pid


def _path_name(path: Path | PurePosixPath) -> str:
    return path.name


def _progress_text(item: TransferItem) -> str:
    if item.size_bytes <= 0:
        return "0%"
    return f"{int(item.bytes_transferred * 100 / item.size_bytes)}%"


def _transfer_headers() -> list[str]:
    return [
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


def _diagnostic_log_record(record) -> dict[str, str]:
    return {
        "timestamp": record.timestamp.isoformat(timespec="seconds"),
        "category": record.category,
        "level": record.level,
        "message": record.message,
    }


def _transfer_retry_diagnostics(items: list[TransferItem], now: datetime) -> dict:
    retrying = [item for item in items if item.status is TransferStatus.RETRYING]
    waiting_retrying = [
        item for item in retrying if item.next_retry_at is not None and item.next_retry_at > now
    ]
    ready_retrying = [
        item for item in retrying if item.next_retry_at is None or item.next_retry_at <= now
    ]
    failures = [
        item
        for item in items
        if item.status in {TransferStatus.FAILED, TransferStatus.RETRYING}
        and (item.failure_reason or item.last_error)
    ]
    next_retry_at = min(
        (item.next_retry_at for item in waiting_retrying if item.next_retry_at is not None),
        default=None,
    )
    return {
        "retrying": {
            "total": len(retrying),
            "ready": len(ready_retrying),
            "waiting": len(waiting_retrying),
            "next_retry_at": next_retry_at.isoformat() if next_retry_at else None,
        },
        "failures": {
            "total": len([item for item in items if item.status is TransferStatus.FAILED]),
            "recent": [_diagnostic_transfer_failure(item) for item in failures[-10:]],
        },
    }


def _diagnostic_transfer_failure(item: TransferItem) -> dict[str, str | int]:
    return {
        "item_id": item.id,
        "task_id": item.task_id,
        "server_id": item.server_id,
        "status": item.status.value,
        "retry_count": item.retry_count,
        "reason": item.failure_reason or item.last_error or "",
    }


def _speed_text(item: TransferItem) -> str:
    if item.bytes_per_second <= 0:
        return ""
    return f"{_human_bytes(item.bytes_per_second)}/s"


def _remaining_text(item: TransferItem) -> str:
    if item.remaining_seconds is None:
        return ""
    seconds = int(item.remaining_seconds)
    if seconds < 60:
        return f"{seconds}s"
    minutes, remainder = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {remainder}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def _status_text(status: TransferStatus) -> str:
    return status.value.replace("_", " ").title()


def _transfer_status_text(item: TransferItem, *, now: datetime | None = None) -> str:
    if item.status is TransferStatus.RETRYING and item.next_retry_at is not None:
        if now is not None and item.next_retry_at > now:
            seconds = max(int((item.next_retry_at - now).total_seconds()), 1)
            return f"Retrying in {seconds}s"
        return "Retrying now"
    return _status_text(item.status)


def _is_terminal_transfer_status(status: TransferStatus) -> bool:
    return status in {
        TransferStatus.COMPLETED,
        TransferStatus.FAILED,
        TransferStatus.CANCELED,
    }


def _transfer_render_key(item: TransferItem) -> tuple[str, str]:
    return (item.task_id, item.id)


class TransferTableModel(QAbstractTableModel):
    def __init__(
        self,
        parent=None,
        *,
        headers: list[str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(parent)
        self._headers = headers or _transfer_headers()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._items: list[TransferItem] = []

    def set_headers(self, headers: list[str]) -> None:
        self.beginResetModel()
        self._headers = headers
        self.endResetModel()

    def set_items(self, items: list[TransferItem]) -> None:
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def refresh_statuses(self) -> None:
        if not self._items:
            return
        first = self.index(0, 8)
        last = self.index(len(self._items) - 1, 8)
        self.dataChanged.emit(first, last, [Qt.ItemDataRole.DisplayRole])

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return 9

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self._item_at(index.row())
        if item is None:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display_text(item, index.column())
        if role == Qt.ItemDataRole.UserRole:
            return item.task_id
        if role == Qt.ItemDataRole.BackgroundRole:
            return QBrush(_transfer_status_color(item.status))
        return None

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
            and 0 <= section < len(self._headers)
        ):
            return self._headers[section]
        return super().headerData(section, orientation, role)

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def _display_text(self, item: TransferItem, column: int) -> str:
        if column == 0:
            return item.server_id
        if column == 1:
            return item.direction.value
        if column == 2:
            return _path_name(item.destination_path)
        if column == 3:
            return _progress_text(item)
        if column == 4:
            return _speed_text(item)
        if column == 5:
            return _remaining_text(item)
        if column == 6:
            return str(item.retry_count)
        if column == 7:
            return item.failure_reason or item.last_error or ""
        if column == 8:
            return _transfer_status_text(item, now=self._clock())
        return ""

    def _item_at(self, row: int) -> TransferItem | None:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None


def _transfer_status_color(status: TransferStatus) -> QColor:
    colors = {
        TransferStatus.PENDING: QColor("#334155"),
        TransferStatus.RUNNING: QColor("#1d4ed8"),
        TransferStatus.PAUSED: QColor("#92400e"),
        TransferStatus.RETRYING: QColor("#b45309"),
        TransferStatus.FAILED: QColor("#991b1b"),
        TransferStatus.COMPLETED: QColor("#166534"),
        TransferStatus.CANCELED: QColor("#475569"),
    }
    return colors.get(status, QColor("#334155"))


def _transfer_summary_text(items: list[TransferItem]) -> str:
    if not items:
        return ""
    task_id = items[0].task_id
    task_items = [item for item in items if item.task_id == task_id]
    if len(task_items) <= 1:
        return ""
    total_bytes = sum(item.size_bytes for item in task_items)
    completed_bytes = sum(item.bytes_transferred for item in task_items)
    current = next(
        (item for item in task_items if item.status is not TransferStatus.COMPLETED),
        task_items[-1],
    )
    return (
        f"{task_id}: {len(task_items)} files, "
        f"{completed_bytes} / {total_bytes} bytes, current {_path_name(current.destination_path)}"
    )


def _log_category_for_message(message: str) -> str:
    lower = message.lower()
    if "failed" in lower or "failure" in lower or "error" in lower:
        return "error"
    if lower.startswith("agent ") or " agent " in lower:
        return "agent"
    if lower.startswith("resource ") or lower.startswith("heartbeat "):
        return "resource"
    if (
        lower.startswith("connect")
        or lower.startswith("disconnect")
        or lower.startswith("connected")
        or lower.startswith("site ")
        or lower.startswith("remote directory")
    ):
        return "connection"
    return "transfer"


def _disk_text(snapshot: ResourceSnapshot, *, mount: str = "All disks") -> str:
    if not snapshot.disks:
        return ""
    disk = next((item for item in snapshot.disks if item.mount == mount), snapshot.disks[0])
    return f"{disk.mount}: {_human_bytes(disk.used_bytes)} / {_human_bytes(disk.total_bytes)}"


def _usage_percent(used: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return used * 100 / total


def _human_bytes(value: int | float) -> str:
    size = float(value)
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if abs(size) < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024


def _protocol_from_label(label: str) -> Protocol:
    mapping = {
        "SFTP": Protocol.SFTP,
        "FTP": Protocol.FTP,
        "FTPS": Protocol.FTPS,
    }
    return mapping.get(label, Protocol.SFTP)


def _choose_local_directory(parent, current: str) -> str:
    return QFileDialog.getExistingDirectory(parent, "Choose Local Directory", current)


def _choose_log_file(parent) -> str:
    path, _selected_filter = QFileDialog.getSaveFileName(
        parent,
        "Export FileZall Logs",
        "filezall.log",
        "Log Files (*.log);;Text Files (*.txt);;All Files (*)",
    )
    return path


def _choose_diagnostic_file(parent) -> str:
    path, _selected_filter = QFileDialog.getSaveFileName(
        parent,
        "Export FileZall Diagnostics",
        "filezall-diagnostics.zip",
        "Zip Files (*.zip);;All Files (*)",
    )
    return path


def _prompt_rename(parent, old_name: str) -> str:
    value, accepted = QInputDialog.getText(parent, "Rename", "New name:", text=old_name)
    return value.strip() if accepted else ""


def _connection_state_key(text: str) -> str:
    lowered = text.lower()
    if lowered.startswith("connecting"):
        return "connecting"
    if lowered.startswith("connected"):
        return "connected"
    if lowered.startswith("disconnecting"):
        return "disconnecting"
    if lowered.startswith("disconnected"):
        return "disconnected"
    if lowered.startswith("failed") or "failed" in lowered:
        return "failed"
    if lowered.startswith("checking"):
        return "checking"
    return lowered.replace(" ", "_")


def _version_is_older(current: str, target: str) -> bool:
    current_parts = _version_parts(current)
    target_parts = _version_parts(target)
    if current_parts is None or target_parts is None:
        return False
    width = max(len(current_parts), len(target_parts))
    current_parts += [0] * (width - len(current_parts))
    target_parts += [0] * (width - len(target_parts))
    return current_parts < target_parts


def _version_parts(value: str) -> list[int] | None:
    try:
        return [int(part) for part in value.split(".")]
    except ValueError:
        return None


def _confirm_agent_install(parent, action: str = "install") -> bool:
    title = "Update FileZall Agent" if action == "update" else "Install FileZall Agent"
    message = (
        "FileZall Agent is already installed on the connected server. "
        "Update it and restart the Agent service?"
        if action == "update"
        else "Install and start FileZall Agent on the connected server?"
    )
    return (
        QMessageBox.question(
            parent,
            title,
            message,
        )
        == QMessageBox.StandardButton.Yes
    )


def _confirm_remember_secret(parent) -> bool:
    return (
        QMessageBox.question(
            parent,
            "Remember Password",
            "Remember this server password for future logins?",
        )
        == QMessageBox.StandardButton.Yes
    )


def _confirm_delete(parent, names: list[str], remote: bool) -> bool:
    target = "remote" if remote else "local"
    sample = ", ".join(names[:3])
    if len(names) > 3:
        sample = f"{sample}, ..."
    return (
        QMessageBox.question(
            parent,
            "Confirm Delete",
            f"Delete {len(names)} {target} item(s)?\n{sample}",
        )
        == QMessageBox.StandardButton.Yes
    )
