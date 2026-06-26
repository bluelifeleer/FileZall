from __future__ import annotations

from collections.abc import Callable
from pathlib import Path, PurePosixPath

from PySide6.QtCore import QObject, QPoint, QRect, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QActionGroup, QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from filezall_core import __version__
from filezall_core.app_paths import resolve_app_paths
from filezall_core.agent_deployment import classify_agent_error
from filezall_core.diagnostics import DiagnosticPackageBuilder
from filezall_core.log_service import TransferLogService
from filezall_core.models import AuthMode, Direction, Protocol, SiteProfile, TransferItem
from filezall_core.resource_models import ProcessDetail, ResourceSnapshot
from filezall_desktop.assets import app_icon
from filezall_desktop.controller import MainWindowController
from filezall_desktop.i18n import (
    EN_LANGUAGE,
    LANGUAGE_LABELS,
    SYSTEM_LANGUAGE,
    ZH_CN_LANGUAGE,
    t,
)
from filezall_desktop.theme import (
    DARK_THEME,
    LIGHT_THEME,
    SYSTEM_THEME,
    THEME_LABELS,
    hover_color_for_theme,
    selected_color_for_theme,
    stylesheet_for_theme,
)
from filezall_desktop.widgets import ConnectionBar, FilePanel


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
        self._should_confirm_remember_secret = controller is None
        self._heartbeat_failed_logged = False
        self._agent_installed: bool | None = False
        self._agent_version: str | None = None
        self._agent_update_available = False
        self._connection_workers = []
        self._active_connection = None
        self._connection_running = False
        self._agent_workers = []
        self._active_agent_action = None
        self._resource_refresh_workers = []
        self._active_resource_refresh = None
        self._resource_refresh_running = False
        self._remote_directory_workers = []
        self._active_remote_directory_load = None
        self._remote_directory_loading = False
        self.setWindowTitle("FileZall")
        self.setWindowIcon(app_icon())
        self.resize(1280, 800)
        self._build_session_menu()
        self._build_help_menu()
        self._build_theme_menu()
        self._build_language_menu()
        self._build_logs_menu()
        self._build_toolbar()
        self._build_central_layout()
        self._apply_button_roles()
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

    def _build_session_menu(self) -> None:
        self.session_menu = QMenu("Session", self)
        self.menuBar().addMenu(self.session_menu)
        self.new_session_action = self.session_menu.addAction("New Session")
        self.new_session_action.setStatusTip("Open a new FileZall connection session")
        self.new_session_action.triggered.connect(self._handle_new_session_clicked)

    def _build_help_menu(self) -> None:
        self.help_menu = QMenu("Help", self)
        self.menuBar().addMenu(self.help_menu)
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

    def _build_theme_menu(self) -> None:
        self.theme_menu = QMenu("Theme", self)
        self.menuBar().addMenu(self.theme_menu)
        self.theme_action_group = QActionGroup(self)
        self.theme_action_group.setExclusive(True)
        self.system_theme_action = self._add_theme_action(SYSTEM_THEME)
        self.light_theme_action = self._add_theme_action(LIGHT_THEME)
        self.dark_theme_action = self._add_theme_action(DARK_THEME)
        self.theme_action_group.triggered.connect(self._handle_theme_action)

    def _add_theme_action(self, theme_name: str):
        action = self.theme_menu.addAction(THEME_LABELS[theme_name])
        action.setCheckable(True)
        action.setData(theme_name)
        self.theme_action_group.addAction(action)
        return action

    def _handle_theme_action(self, action) -> None:
        self._apply_theme(action.data())

    def _apply_theme(self, theme_name: str) -> None:
        self.current_theme = theme_name
        for action in self.theme_action_group.actions():
            action.setChecked(action.data() == theme_name)
        self.setStyleSheet(stylesheet_for_theme(theme_name))
        hover_color = hover_color_for_theme(theme_name)
        selected_color = selected_color_for_theme(theme_name)
        for panel in (getattr(self, "local_panel", None), getattr(self, "remote_panel", None)):
            if panel is not None:
                panel.table.set_full_row_hover_color(hover_color)
                panel.table.set_full_row_selected_color(selected_color)

    def _build_language_menu(self) -> None:
        self.language_menu = QMenu("Language", self)
        self.menuBar().addMenu(self.language_menu)
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
        self.help_menu.setTitle(self._text("menu.help"))
        self.theme_menu.setTitle(self._text("menu.theme"))
        self.language_menu.setTitle(self._text("menu.language"))
        if hasattr(self, "logs_menu"):
            self.logs_menu.setTitle(self._text("menu.logs"))
            self.export_logs_action.setText(self._text("logs.export"))
            self.export_diagnostics_action.setText(self._text("logs.export_diagnostics"))

        self.about_action.setText(self._text("help.about"))
        self.version_action.setText(self._text("help.version"))
        self.protocols_action.setText(self._text("help.protocols"))
        self.commercial_action.setText(self._text("help.commercial"))

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
                ["Server", "Direction", "File", "Progress", "Status"]
            )
            self.transfer_center_label.setText(self._text("transfer.center"))
            self.transfer_logs_label.setText(self._text("transfer.logs"))
            self.pause_transfer_button.setText(self._text("transfer.pause"))
            self.resume_transfer_button.setText(self._text("transfer.resume"))
            self.cancel_transfer_button.setText(self._text("transfer.cancel"))
            self.retry_transfer_button.setText(self._text("transfer.retry"))
            self.resource_refresh_button.setText(self._text("resource.refresh"))
            self.process_detail_button.setText(self._text("resource.show_process"))
            self.resource_install_agent_button.setText(self._text("resource.install_agent"))
            self.resource_uninstall_agent_button.setText(self._text("resource.uninstall_agent"))
            self.resource_monitor_label.setText(self._text("resource.monitor"))
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
        self.transfer_table = QTableWidget(0, 5, transfer_widget)
        self.transfer_table.setHorizontalHeaderLabels(
            ["Server", "Direction", "File", "Progress", "Status"]
        )
        self.log_view = QPlainTextEdit(transfer_widget)
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(1000)
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
        transfer_actions.addWidget(self.transfer_center_label)
        transfer_actions.addStretch(1)
        transfer_actions.addWidget(self.pause_transfer_button)
        transfer_actions.addWidget(self.resume_transfer_button)
        transfer_actions.addWidget(self.cancel_transfer_button)
        transfer_actions.addWidget(self.retry_transfer_button)
        self.monitoring_status_label = QLabel("", transfer_widget)

        transfer_layout.addLayout(transfer_actions, stretch=0)
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
        resource_actions.addWidget(self.resource_monitor_label)
        resource_actions.addWidget(self.agent_status_label)
        resource_actions.addStretch(1)
        resource_actions.addWidget(self.resource_install_agent_button)
        resource_actions.addWidget(self.resource_uninstall_agent_button)
        resource_actions.addWidget(self.resource_refresh_button)
        resource_actions.addWidget(self.process_detail_button)

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

        self.process_table = QTableWidget(0, 5, root)
        self.process_table.setHorizontalHeaderLabels(["PID", "User", "Name", "CPU", "Memory"])
        self.process_detail_label = QLabel("", root)
        self.resource_chart = ResourceUsageChart(root)
        self.resource_content_splitter = QSplitter(Qt.Orientation.Horizontal, resource_widget)
        self.resource_content_splitter.addWidget(self.process_table)
        self.resource_content_splitter.addWidget(self.resource_chart)
        self.resource_content_splitter.setSizes([760, 360])

        resource_layout.addLayout(resource_actions, stretch=0)
        resource_layout.addLayout(resource_values, stretch=0)
        resource_layout.addWidget(self.resource_content_splitter, stretch=1)
        resource_layout.addWidget(self.process_detail_label, stretch=0)

        self.main_splitter.addWidget(self.file_splitter)
        self.main_splitter.addWidget(transfer_widget)
        self.main_splitter.addWidget(resource_widget)
        self.main_splitter.setSizes([420, 190, 190])
        root_layout.addWidget(self.main_splitter)
        self.setCentralWidget(root)

    def _apply_button_roles(self) -> None:
        role_map = {
            self.connection_bar.connect_button: "primary",
            self.connection_bar.disconnect_button: "danger",
            self.connection_bar.install_agent_button: "success",
            self.local_panel.refresh_button: "secondary",
            self.remote_panel.refresh_button: "secondary",
            self.local_panel.action_button: "primary",
            self.remote_panel.action_button: "primary",
            self.pause_transfer_button: "secondary",
            self.resume_transfer_button: "success",
            self.cancel_transfer_button: "danger",
            self.retry_transfer_button: "secondary",
            self.resource_install_agent_button: "success",
            self.resource_uninstall_agent_button: "danger",
            self.resource_refresh_button: "primary",
            self.process_detail_button: "secondary",
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
        self.statusBar().showMessage(message)

    @Slot(str)
    def append_log(self, message: str) -> None:
        entry = self.log_service.append(message)
        self.log_view.appendPlainText(entry.format())

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
        ).build(Path(selected))
        self.show_status(f"Exported diagnostics to {selected}")

    def set_monitoring_status(self, message: str) -> None:
        self.monitoring_status_label.setText(message)
        if "Agent" in message:
            self.set_agent_status(False)
            self.resource_install_agent_button.show()
            self.resource_uninstall_agent_button.show()
        else:
            self.agent_status_label.setText("")
            self.resource_install_agent_button.hide()
            self.resource_uninstall_agent_button.hide()

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
                self.resource_install_agent_button.show()
                self.resource_uninstall_agent_button.show()
                return
            suffix = f" v{self._agent_version}" if self._agent_version else ""
            self.agent_status_label.setText(f"Agent installed{suffix}")
            self.resource_install_agent_button.setText(self._text("resource.install_agent"))
            self.resource_install_agent_button.hide()
            self.resource_uninstall_agent_button.show()
        else:
            self.agent_status_label.setText("Agent not installed")
            self.resource_install_agent_button.setText(self._text("resource.install_agent"))
            self.resource_install_agent_button.show()
            self.resource_uninstall_agent_button.show()

    def set_agent_version(self, version: str | None) -> None:
        self._agent_version = version
        if self._agent_installed is True:
            self.set_agent_status(True, version=version)

    def set_transfer_items(self, items: list[TransferItem]) -> None:
        self.transfer_table.setRowCount(len(items))
        for row, item in enumerate(items):
            server_cell = QTableWidgetItem(item.server_id)
            server_cell.setData(Qt.ItemDataRole.UserRole, item.task_id)
            self.transfer_table.setItem(row, 0, server_cell)
            self.transfer_table.setItem(row, 1, QTableWidgetItem(item.direction.value))
            self.transfer_table.setItem(row, 2, QTableWidgetItem(_path_name(item.destination_path)))
            self.transfer_table.setItem(row, 3, QTableWidgetItem(_progress_text(item)))
            self.transfer_table.setItem(row, 4, QTableWidgetItem(item.status.value))

    def set_resource_snapshot(self, snapshot: ResourceSnapshot) -> None:
        self.cpu_value_label.setText(f"{snapshot.cpu.percent:.1f}%")
        self.memory_value_label.setText(
            f"{_human_bytes(snapshot.memory.used_bytes)} / {_human_bytes(snapshot.memory.total_bytes)}"
        )
        self.disk_value_label.setText(_disk_text(snapshot))
        self.network_value_label.setText(
            f"RX {_human_bytes(snapshot.network.rx_bytes_per_sec)}/s, "
            f"TX {_human_bytes(snapshot.network.tx_bytes_per_sec)}/s"
        )
        self.resource_chart.add_snapshot(snapshot)
        self.process_table.setRowCount(len(snapshot.processes))
        for row, process in enumerate(snapshot.processes):
            pid_cell = QTableWidgetItem(str(process.pid))
            pid_cell.setData(Qt.ItemDataRole.UserRole, process.pid)
            self.process_table.setItem(row, 0, pid_cell)
            self.process_table.setItem(row, 1, QTableWidgetItem(process.user))
            self.process_table.setItem(row, 2, QTableWidgetItem(process.name))
            self.process_table.setItem(row, 3, QTableWidgetItem(f"{process.cpu_percent:.1f}%"))
            self.process_table.setItem(row, 4, QTableWidgetItem(f"{process.memory_percent:.1f}%"))

    def set_process_detail(self, detail: ProcessDetail) -> None:
        self.process_detail_label.setText(
            f"PID {detail.pid} {detail.name} | user: {detail.user} | "
            f"status: {detail.status} | threads: {detail.thread_count} | {detail.command_line}"
        )

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
        self.pause_transfer_button.clicked.connect(self._handle_pause_transfer_clicked)
        self.resume_transfer_button.clicked.connect(self._handle_resume_transfer_clicked)
        self.cancel_transfer_button.clicked.connect(self._handle_cancel_transfer_clicked)
        self.retry_transfer_button.clicked.connect(self._handle_retry_transfer_clicked)
        self.resource_refresh_button.clicked.connect(self._handle_resource_refresh_tick)
        self.resource_install_agent_button.clicked.connect(self._handle_install_agent_clicked)
        self.resource_uninstall_agent_button.clicked.connect(self._handle_uninstall_agent_clicked)
        self.process_detail_button.clicked.connect(self._handle_process_detail_clicked)

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
            self.append_log(f"Connection failed: {exc}")
            self._set_connection_state("Failed", "red")
            self.heartbeat_timer.stop()
            self.connection_bar.connect_button.setEnabled(True)
            self.show_status(str(exc))
            return
        self._heartbeat_failed_logged = False
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
        self._set_connection_state("Connected", "green")
        self.heartbeat_timer.start()
        self.resource_refresh_timer.start()
        if not isinstance(result, dict) or result.get("resource_snapshot") is None:
            self._handle_resource_refresh_tick()
        self.connection_bar.connect_button.setEnabled(True)
        self._cleanup_connection_worker()

    @Slot(str)
    def _fail_connection(self, error: str) -> None:
        self._append_background_failure("connection", error)
        self.append_log(f"Connection failed: {error}")
        self._set_connection_state("Failed", "red")
        self.heartbeat_timer.stop()
        self.resource_refresh_timer.stop()
        self.connection_bar.connect_button.setEnabled(True)
        self.show_status(error)
        self._cleanup_connection_worker()

    def _publish_connection_result(self, result) -> None:
        if not isinstance(result, dict):
            return
        self.set_remote_entries(result["entries"], result["remote_path"])
        self.set_monitoring_status(result["monitoring_status"])
        for status in result.get("agent_status_sequence", []):
            self.set_agent_status(status)
        agent_status = result.get("agent_status")
        if agent_status is not None and not result.get("agent_status_sequence"):
            self.set_agent_status(agent_status)
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
        thread = QThread(self)
        worker = AgentActionWorker(action)
        worker.moveToThread(thread)
        self._active_agent_action = (label, thread, worker, complete)
        self._agent_workers.append((thread, worker))
        thread.started.connect(worker.run)
        worker.progress.connect(self.append_log, Qt.ConnectionType.QueuedConnection)
        worker.succeeded.connect(self._finish_agent_action, Qt.ConnectionType.QueuedConnection)
        worker.failed.connect(self._fail_agent_action, Qt.ConnectionType.QueuedConnection)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

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
        self.append_log(f"Agent {label} command finished")
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
        self._load_remote_directory(remote_path)

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

    def _load_remote_directory(self, path: PurePosixPath) -> None:
        if self._remote_directory_loading:
            self.show_status("Remote directory load already in progress")
            return
        self.remote_panel.path_edit.add_history(str(path))
        self._set_remote_loading(True, path)
        if not hasattr(self.controller, "load_remote_directory"):
            try:
                self.controller.list_remote_directory(path)
            finally:
                self._set_remote_loading(False, path)
            return
        self._remote_directory_loading = True
        thread = QThread(self)
        worker = RemoteDirectoryWorker(lambda: self.controller.load_remote_directory(path))
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

    def _set_remote_loading(self, loading: bool, path: PurePosixPath) -> None:
        enabled = not loading
        self.remote_panel.table.setEnabled(enabled)
        self.remote_panel.refresh_button.setEnabled(enabled)
        self.remote_panel.path_button.setEnabled(enabled)
        self.remote_panel.action_button.setEnabled(enabled)
        if loading:
            self.show_status(self._text("status.loading_remote", path=path))

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

    def _handle_upload_clicked(self) -> None:
        local_root = Path(self.local_panel.path_edit.text().strip() or Path.home())
        for local_name in self.local_panel.selected_names():
            local_path = local_root / local_name
            self.controller.upload_file(local_path, self._remote_path_from_field() / local_name)

    def _handle_download_clicked(self) -> None:
        local_root = Path(self.local_panel.path_edit.text().strip() or Path.home())
        for remote_name in self.remote_panel.selected_names():
            self.controller.download_file(
                self._remote_path_from_field() / remote_name,
                local_root / remote_name,
            )

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

    def _handle_local_delete_action(self) -> None:
        for local_name in self.local_panel.selected_names():
            self.controller.delete_path(self._local_root() / local_name, remote=False)

    def _handle_remote_delete_action(self) -> None:
        for remote_name in self.remote_panel.selected_names():
            self.controller.delete_path(self._remote_path_from_field() / remote_name, remote=True)

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
        source = self._remote_path_from_field() / name
        self.controller.rename_path(source, source.parent / new_name, remote=True)

    def _handle_local_copy_path_action(self) -> None:
        paths = [str(self._local_root() / name) for name in self.local_panel.selected_names()]
        self._copy_paths(paths)

    def _handle_remote_copy_path_action(self) -> None:
        paths = [str(self._remote_path_from_field() / name) for name in self.remote_panel.selected_names()]
        self._copy_paths(paths)

    def _copy_paths(self, paths: list[str]) -> None:
        if not paths:
            return
        QApplication.clipboard().setText("\n".join(paths))
        self.show_status(f"Copied {len(paths)} path(s)")
        self.append_log(f"Copied {len(paths)} path(s)")

    def _handle_local_create_dir_action(self) -> None:
        self.controller.create_directory(self._local_root(), remote=False)

    def _handle_remote_create_dir_action(self) -> None:
        self.controller.create_directory(self._remote_path_from_field(), remote=True)

    def _handle_local_create_file_action(self) -> None:
        self.controller.create_file(self._local_root(), remote=False)

    def _handle_remote_create_file_action(self) -> None:
        self.controller.create_file(self._remote_path_from_field(), remote=True)

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
        if pid := self._selected_process_id():
            self.controller.show_process_detail(pid)

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
        self._blink_connection_state("goldenrod")
        try:
            ok = self.controller.heartbeat()
        except Exception as exc:
            self._log_heartbeat_failure(f"Heartbeat failed: {exc}")
            self._set_connection_state(f"Disconnected: {exc}", "red")
            return
        if ok:
            self._heartbeat_failed_logged = False
            self._set_connection_state("Connected", "green")
        else:
            self._log_heartbeat_failure("Heartbeat failed: disconnected")
            self._set_connection_state("Disconnected", "red")

    def _log_heartbeat_failure(self, message: str) -> None:
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


def _path_name(path: Path | PurePosixPath) -> str:
    return path.name


def _progress_text(item: TransferItem) -> str:
    if item.size_bytes <= 0:
        return "0%"
    return f"{int(item.bytes_transferred * 100 / item.size_bytes)}%"


def _disk_text(snapshot: ResourceSnapshot) -> str:
    if not snapshot.disks:
        return ""
    disk = snapshot.disks[0]
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
