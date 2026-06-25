from __future__ import annotations

from pathlib import Path, PurePosixPath

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
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
from filezall_core.log_service import TransferLogService
from filezall_core.models import AuthMode, Direction, Protocol, SiteProfile, TransferItem
from filezall_core.resource_models import ProcessDetail, ResourceSnapshot
from filezall_desktop.assets import app_icon
from filezall_desktop.controller import MainWindowController
from filezall_desktop.widgets import ConnectionBar, FilePanel


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
    ) -> None:
        super().__init__()
        self.log_service = TransferLogService()
        self.site_profiles = []
        self._site_secret_lookup = None
        self._local_directory_chooser = local_directory_chooser or _choose_local_directory
        self._agent_install_confirmer = agent_install_confirmer or _confirm_agent_install
        self._remember_secret_confirmer = remember_secret_confirmer
        self._log_file_chooser = log_file_chooser or _choose_log_file
        self._should_confirm_remember_secret = controller is None
        self.setWindowTitle("FileZall")
        self.setWindowIcon(app_icon())
        self.resize(1280, 800)
        self._build_help_menu()
        self._build_logs_menu()
        self._build_toolbar()
        self._build_central_layout()
        self.setStatusBar(QStatusBar(self))
        self.connection_state_label = QLabel("", self)
        self.connection_state_label.setFixedSize(12, 12)
        self.statusBar().addPermanentWidget(self.connection_state_label)
        self._set_connection_state("Idle", "grey")
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.setInterval(10_000)
        self.heartbeat_timer.timeout.connect(self._handle_heartbeat_tick)
        self.statusBar().showMessage("Ready")
        self.controller = controller or MainWindowController(
            self,
            site_repository=site_repository,
            credential_service=credential_service,
            queue_service=queue_service,
            log_service=self.log_service,
        )
        self._connect_signals()
        self.controller.load_saved_sites()

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

    def _build_logs_menu(self) -> None:
        self.logs_menu = QMenu("Logs", self)
        self.menuBar().addMenu(self.logs_menu)
        self.export_logs_action = self.logs_menu.addAction("Export Logs")
        self.export_logs_action.setStatusTip("Export FileZall transfer and connection logs")
        self.export_logs_action.triggered.connect(self._export_logs)

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
        transfer_actions.addWidget(QLabel("Transfer Center", root))
        transfer_actions.addStretch(1)
        transfer_actions.addWidget(self.pause_transfer_button)
        transfer_actions.addWidget(self.resume_transfer_button)
        transfer_actions.addWidget(self.cancel_transfer_button)
        transfer_actions.addWidget(self.retry_transfer_button)
        self.monitoring_status_label = QLabel("", transfer_widget)

        transfer_layout.addLayout(transfer_actions, stretch=0)
        transfer_layout.addWidget(self.monitoring_status_label, stretch=0)
        transfer_layout.addWidget(QLabel("Transfer Logs", transfer_widget), stretch=0)
        transfer_layout.addWidget(self.transfer_splitter, stretch=1)

        resource_widget = QWidget(self.main_splitter)
        resource_layout = QVBoxLayout(resource_widget)
        resource_actions = QHBoxLayout()
        self.resource_refresh_button = QPushButton("Refresh Resources", root)
        self.process_detail_button = QPushButton("Process Detail", root)
        self.agent_status_label = QLabel("", resource_widget)
        self.resource_install_agent_button = QPushButton("Install Agent", resource_widget)
        self.resource_install_agent_button.hide()
        resource_actions.addWidget(QLabel("Resource Monitor", root))
        resource_actions.addWidget(self.agent_status_label)
        resource_actions.addStretch(1)
        resource_actions.addWidget(self.resource_install_agent_button)
        resource_actions.addWidget(self.resource_refresh_button)
        resource_actions.addWidget(self.process_detail_button)

        resource_values = QHBoxLayout()
        self.cpu_value_label = QLabel("0.0%", root)
        self.memory_value_label = QLabel("0 / 0 bytes", root)
        self.disk_value_label = QLabel("", root)
        self.network_value_label = QLabel("RX 0 B/s, TX 0 B/s", root)
        resource_values.addWidget(QLabel("CPU", root))
        resource_values.addWidget(self.cpu_value_label)
        resource_values.addWidget(QLabel("Memory", root))
        resource_values.addWidget(self.memory_value_label)
        resource_values.addWidget(QLabel("Disk", root))
        resource_values.addWidget(self.disk_value_label)
        resource_values.addWidget(QLabel("Network", root))
        resource_values.addWidget(self.network_value_label)

        self.process_table = QTableWidget(0, 5, root)
        self.process_table.setHorizontalHeaderLabels(["PID", "User", "Name", "CPU", "Memory"])
        self.process_detail_label = QLabel("", root)

        resource_layout.addLayout(resource_actions, stretch=0)
        resource_layout.addLayout(resource_values, stretch=0)
        resource_layout.addWidget(self.process_table, stretch=1)
        resource_layout.addWidget(self.process_detail_label, stretch=0)

        self.main_splitter.addWidget(self.file_splitter)
        self.main_splitter.addWidget(transfer_widget)
        self.main_splitter.addWidget(resource_widget)
        self.main_splitter.setSizes([420, 190, 190])
        root_layout.addWidget(self.main_splitter)
        self.setCentralWidget(root)

    def set_local_entries(self, entries) -> None:
        self.local_panel.set_entries(entries)

    def set_remote_entries(self, entries, path) -> None:
        self.remote_panel.path_edit.setText(str(path or ""))
        self.remote_panel.set_entries(entries)

    def show_status(self, message: str) -> None:
        self.statusBar().showMessage(message)

    def append_log(self, message: str) -> None:
        entry = self.log_service.append(message)
        self.log_view.appendPlainText(entry.format())

    def _export_logs(self) -> None:
        selected = self._log_file_chooser(self)
        if not selected:
            return
        self.log_service.export(Path(selected))
        self.show_status(f"Exported logs to {selected}")

    def set_monitoring_status(self, message: str) -> None:
        self.monitoring_status_label.setText(message)
        if "Agent" in message:
            self.agent_status_label.setText("Agent not installed")
            self.resource_install_agent_button.show()
        else:
            self.agent_status_label.setText("")
            self.resource_install_agent_button.hide()

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
            f"{snapshot.memory.used_bytes} / {snapshot.memory.total_bytes} bytes"
        )
        self.disk_value_label.setText(_disk_text(snapshot))
        self.network_value_label.setText(
            f"RX {snapshot.network.rx_bytes_per_sec} B/s, TX {snapshot.network.tx_bytes_per_sec} B/s"
        )
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
        self.connection_bar.site_selector.addItem("Quick Connect")
        for site in self.site_profiles:
            self.connection_bar.site_selector.addItem(site.name, site.id)
        if self.site_profiles:
            self.connection_bar.site_selector.setCurrentIndex(1)
            self._populate_connection_fields(self.site_profiles[0])

    def _connect_signals(self) -> None:
        self.connection_bar.connect_button.clicked.connect(self._handle_connect_clicked)
        self.connection_bar.site_selector.currentIndexChanged.connect(
            self._handle_site_selection_changed
        )
        self.connection_bar.install_agent_button.clicked.connect(self._handle_install_agent_clicked)
        self.local_panel.path_button.clicked.connect(self._handle_local_path_button_clicked)
        self.remote_panel.path_button.clicked.connect(self._handle_remote_path_button_clicked)
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
        self.resource_refresh_button.clicked.connect(self.controller.refresh_resources)
        self.resource_install_agent_button.clicked.connect(self._handle_install_agent_clicked)
        self.process_detail_button.clicked.connect(self._handle_process_detail_clicked)

    def _handle_connect_clicked(self) -> None:
        site = self._selected_saved_site()
        secret = None if site else self._secret_from_fields()
        remember_secret = True
        if not site and secret:
            if self._remember_secret_confirmer is not None:
                remember_secret = self._remember_secret_confirmer(self)
            elif self._should_confirm_remember_secret:
                remember_secret = _confirm_remember_secret(self)
        self._set_connection_state("Connecting", "goldenrod")
        self.connection_bar.connect_button.setEnabled(False)
        try:
            self.controller.connect(
                site or self._site_from_fields(),
                secret,
                remember_secret=remember_secret,
            )
        except Exception as exc:
            self._set_connection_state("Failed", "red")
            self.heartbeat_timer.stop()
            self.connection_bar.connect_button.setEnabled(True)
            self.show_status(str(exc))
            return
        self._set_connection_state("Connected", "green")
        self.heartbeat_timer.start()
        self.connection_bar.connect_button.setEnabled(True)

    def _handle_install_agent_clicked(self) -> None:
        if self._agent_install_confirmer(self):
            self.controller.install_agent()

    def _handle_local_refresh_clicked(self) -> None:
        self.local_panel.clear_selection()
        path_text = self.local_panel.path_edit.text().strip()
        self.controller.load_local_directory(Path(path_text) if path_text else Path.home())

    def _handle_remote_refresh_clicked(self) -> None:
        self.remote_panel.clear_selection()
        remote_path = self._remote_path_from_field()
        self.controller.list_remote_directory(remote_path)

    def _handle_local_path_button_clicked(self) -> None:
        current = self.local_panel.path_edit.text().strip() or str(Path.home())
        selected = self._local_directory_chooser(self, current)
        if not selected:
            return
        path = Path(selected)
        self.local_panel.path_edit.setText(str(path))
        self.local_panel.clear_selection()
        self.controller.load_local_directory(path)

    def _handle_remote_path_button_clicked(self) -> None:
        remote_name = self.remote_panel.selected_name()
        if not remote_name or not self.remote_panel.selected_is_dir():
            self.show_status("Select a remote directory to open")
            return
        self.remote_panel.clear_selection()
        self.controller.list_remote_directory(self._remote_path_from_field() / remote_name)

    def _handle_local_double_clicked(self, row: int, _column: int) -> None:
        if self.local_panel.is_parent_at(row):
            self.controller.load_local_directory(self._local_parent())
            return
        if not self.local_panel.is_dir_at(row):
            return
        name = self.local_panel.name_at(row)
        if name:
            self.controller.load_local_directory(self._local_root() / name)

    def _handle_remote_double_clicked(self, row: int, _column: int) -> None:
        if self.remote_panel.is_parent_at(row):
            self.controller.list_remote_directory(self._remote_parent())
            return
        if not self.remote_panel.is_dir_at(row):
            return
        name = self.remote_panel.name_at(row)
        if name:
            self.controller.list_remote_directory(self._remote_path_from_field() / name)

    def _handle_local_clicked(self, row: int, _column: int) -> None:
        if self.local_panel.is_parent_at(row):
            self.controller.load_local_directory(self._local_parent())

    def _handle_remote_clicked(self, row: int, _column: int) -> None:
        if self.remote_panel.is_parent_at(row):
            self.controller.list_remote_directory(self._remote_parent())

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

    def _handle_heartbeat_tick(self) -> None:
        self._set_connection_state("Checking", "goldenrod")
        try:
            ok = self.controller.heartbeat()
        except Exception as exc:
            self._set_connection_state(f"Disconnected: {exc}", "red")
            return
        if ok:
            self._set_connection_state("Connected", "green")
        else:
            self._set_connection_state("Disconnected", "red")

    def _set_connection_state(self, text: str, color: str) -> None:
        self.connection_state_label.setText("")
        self.connection_state_label.setToolTip(text)
        self.connection_state_label.setStyleSheet(
            "border-radius: 6px; "
            f"background-color: {color}; "
            f"border: 1px solid {color};"
        )

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
        self.connection_bar.auth_mode_selector.setCurrentText(
            "SSH Key" if site.auth_mode == AuthMode.SSH_KEY else "Password"
        )
        self.connection_bar.ssh_key_path_edit.setText(str(site.ssh_key_path or ""))
        self.local_panel.path_edit.setText(str(site.default_local_path or ""))
        self.remote_panel.path_edit.setText(str(site.default_remote_path))
        secret = self._site_secret_lookup(site) if self._site_secret_lookup else None
        self.connection_bar.secret_edit.setText(secret or "")

    def _site_from_fields(self) -> SiteProfile:
        host = self.connection_bar.host_edit.text().strip()
        username = self.connection_bar.username_edit.text().strip()
        auth_mode = (
            AuthMode.SSH_KEY
            if self.connection_bar.auth_mode_selector.currentText() == "SSH Key"
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
    return f"{disk.mount}: {disk.used_bytes} / {disk.total_bytes} bytes"


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


def _confirm_agent_install(parent) -> bool:
    return (
        QMessageBox.question(
            parent,
            "Install FileZall Agent",
            "Install and start FileZall Agent on the connected server?",
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
