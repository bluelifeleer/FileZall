from __future__ import annotations

from pathlib import Path, PurePosixPath

from PySide6.QtWidgets import QLabel, QMainWindow, QSplitter, QStatusBar, QTableWidget, QToolBar, QVBoxLayout, QWidget

from filezall_core.models import AuthMode, Protocol, SiteProfile
from filezall_desktop.controller import MainWindowController
from filezall_desktop.widgets import ConnectionBar, FilePanel


class MainWindow(QMainWindow):
    def __init__(
        self,
        controller=None,
        site_repository=None,
        credential_service=None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("FileZall")
        self.resize(1280, 800)
        self._build_toolbar()
        self._build_central_layout()
        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("Ready")
        self.controller = controller or MainWindowController(
            self,
            site_repository=site_repository,
            credential_service=credential_service,
        )
        self._connect_signals()
        self.controller.load_saved_sites()

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Connection")
        toolbar.setMovable(False)
        self.connection_bar = ConnectionBar(self)
        toolbar.addWidget(self.connection_bar)
        self.addToolBar(toolbar)

    def _build_central_layout(self) -> None:
        root = QWidget(self)
        root_layout = QVBoxLayout(root)

        file_splitter = QSplitter(root)
        self.local_panel = FilePanel("Local Files", "Upload", self)
        self.remote_panel = FilePanel("Remote Files", "Download", self)
        self.local_panel.set_placeholder_row("No directory loaded")
        self.remote_panel.set_placeholder_row("Not connected")
        file_splitter.addWidget(self.local_panel)
        file_splitter.addWidget(self.remote_panel)
        file_splitter.setSizes([640, 640])

        self.transfer_table = QTableWidget(0, 5, root)
        self.transfer_table.setHorizontalHeaderLabels(
            ["Server", "Direction", "File", "Progress", "Status"]
        )

        root_layout.addWidget(file_splitter, stretch=4)
        root_layout.addWidget(QLabel("Transfer Center"), stretch=0)
        root_layout.addWidget(self.transfer_table, stretch=1)
        self.setCentralWidget(root)

    def set_local_entries(self, entries) -> None:
        self.local_panel.set_entries(entries)

    def set_remote_entries(self, entries, path) -> None:
        self.remote_panel.path_edit.setText(str(path or ""))
        self.remote_panel.set_entries(entries)

    def show_status(self, message: str) -> None:
        self.statusBar().showMessage(message)

    def set_site_profiles(self, sites) -> None:
        self.site_profiles = list(sites)
        self.connection_bar.site_selector.clear()
        self.connection_bar.site_selector.addItem("Quick Connect")
        for site in self.site_profiles:
            self.connection_bar.site_selector.addItem(site.name, site.id)

    def _connect_signals(self) -> None:
        self.connection_bar.connect_button.clicked.connect(self._handle_connect_clicked)
        self.local_panel.refresh_button.clicked.connect(self._handle_local_refresh_clicked)
        self.remote_panel.refresh_button.clicked.connect(self._handle_remote_refresh_clicked)
        self.local_panel.action_button.clicked.connect(self._handle_upload_clicked)
        self.remote_panel.action_button.clicked.connect(self._handle_download_clicked)

    def _handle_connect_clicked(self) -> None:
        site = self._selected_saved_site()
        self.controller.connect(site or self._site_from_fields(), None if site else self._secret_from_fields())

    def _handle_local_refresh_clicked(self) -> None:
        path_text = self.local_panel.path_edit.text().strip()
        self.controller.load_local_directory(Path(path_text) if path_text else Path.home())

    def _handle_remote_refresh_clicked(self) -> None:
        remote_path = self._remote_path_from_field()
        self.controller.list_remote_directory(remote_path)

    def _handle_upload_clicked(self) -> None:
        local_name = self.local_panel.selected_name()
        if not local_name:
            return
        local_root = Path(self.local_panel.path_edit.text().strip() or Path.home())
        local_path = local_root / local_name
        self.controller.upload_file(local_path, self._remote_path_from_field() / local_name)

    def _handle_download_clicked(self) -> None:
        remote_name = self.remote_panel.selected_name()
        if not remote_name:
            return
        local_root = Path(self.local_panel.path_edit.text().strip() or Path.home())
        self.controller.download_file(self._remote_path_from_field() / remote_name, local_root / remote_name)

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
            protocol=Protocol.SFTP,
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
