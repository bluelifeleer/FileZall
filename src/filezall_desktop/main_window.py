from __future__ import annotations

from PySide6.QtWidgets import QLabel, QMainWindow, QSplitter, QStatusBar, QTableWidget, QToolBar, QVBoxLayout, QWidget

from filezall_desktop.widgets import ConnectionBar, FilePanel


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FileZall")
        self.resize(1280, 800)
        self._build_toolbar()
        self._build_central_layout()
        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("Ready")

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
        self.local_panel = FilePanel("Local Files", self)
        self.remote_panel = FilePanel("Remote Files", self)
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
