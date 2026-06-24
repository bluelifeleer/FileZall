from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)


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
        toolbar.addWidget(QLabel("Site"))
        toolbar.addSeparator()
        toolbar.addAction("Connect")
        toolbar.addAction("Disconnect")
        self.addToolBar(toolbar)

    def _build_central_layout(self) -> None:
        root = QWidget(self)
        root_layout = QVBoxLayout(root)

        file_splitter = QSplitter(root)
        file_splitter.addWidget(self._build_file_panel("Local Files"))
        file_splitter.addWidget(self._build_file_panel("Remote Files"))
        file_splitter.setSizes([640, 640])

        transfer_table = QTableWidget(0, 5, root)
        transfer_table.setHorizontalHeaderLabels(
            ["Server", "Direction", "File", "Progress", "Status"]
        )

        root_layout.addWidget(file_splitter, stretch=4)
        root_layout.addWidget(QLabel("Transfer Center"), stretch=0)
        root_layout.addWidget(transfer_table, stretch=1)
        self.setCentralWidget(root)

    def _build_file_panel(self, title: str) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        header = QHBoxLayout()
        header.addWidget(QLabel(title))
        header.addStretch()
        header.addWidget(QPushButton("Refresh"))

        table = QTableWidget(1, 4, panel)
        table.setHorizontalHeaderLabels(["Name", "Size", "Type", "Modified"])
        table.setItem(0, 0, QTableWidgetItem("No directory loaded"))
        table.setItem(0, 1, QTableWidgetItem(""))
        table.setItem(0, 2, QTableWidgetItem(""))
        table.setItem(0, 3, QTableWidgetItem(""))

        layout.addLayout(header)
        layout.addWidget(table)
        return panel
