from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ConnectionBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        self.site_selector = QComboBox(self)
        self.site_selector.addItem("Quick Connect")
        self.host_edit = QLineEdit(self)
        self.host_edit.setPlaceholderText("Host")
        self.port_edit = QLineEdit("22", self)
        self.port_edit.setFixedWidth(64)
        self.username_edit = QLineEdit(self)
        self.username_edit.setPlaceholderText("Username")
        self.auth_mode_selector = QComboBox(self)
        self.auth_mode_selector.addItems(["Password", "SSH Key"])
        self.secret_edit = QLineEdit(self)
        self.secret_edit.setPlaceholderText("Password / passphrase")
        self.secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.ssh_key_path_edit = QLineEdit(self)
        self.ssh_key_path_edit.setPlaceholderText("SSH key path")
        self.protocol_selector = QComboBox(self)
        self.protocol_selector.addItems(["SFTP"])
        self.connect_button = QPushButton("Connect", self)
        self.disconnect_button = QPushButton("Disconnect", self)

        layout.addWidget(QLabel("Site", self))
        layout.addWidget(self.site_selector)
        layout.addWidget(self.host_edit)
        layout.addWidget(self.port_edit)
        layout.addWidget(self.username_edit)
        layout.addWidget(self.auth_mode_selector)
        layout.addWidget(self.secret_edit)
        layout.addWidget(self.ssh_key_path_edit)
        layout.addWidget(self.protocol_selector)
        layout.addWidget(self.connect_button)
        layout.addWidget(self.disconnect_button)


class FilePanel(QWidget):
    def __init__(
        self,
        title: str,
        action_label: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self.title = QLabel(title, self)
        self.path_edit = QLineEdit(self)
        self.refresh_button = QPushButton("Refresh", self)
        self.action_button = QPushButton(action_label, self)
        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["Name", "Size", "Type", "Modified"])

        header.addWidget(self.title)
        header.addWidget(self.path_edit)
        header.addWidget(self.refresh_button)
        header.addWidget(self.action_button)
        layout.addLayout(header)
        layout.addWidget(self.table)

    def set_placeholder_row(self, text: str) -> None:
        self.table.setRowCount(1)
        self.table.setItem(0, 0, QTableWidgetItem(text))
        self.table.setItem(0, 1, QTableWidgetItem(""))
        self.table.setItem(0, 2, QTableWidgetItem(""))
        self.table.setItem(0, 3, QTableWidgetItem(""))

    def set_entries(self, entries) -> None:
        self.table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            self.table.setItem(row, 0, QTableWidgetItem(entry.name))
            self.table.setItem(row, 1, QTableWidgetItem(str(entry.size_bytes)))
            self.table.setItem(row, 2, QTableWidgetItem("Directory" if entry.is_dir else "File"))
            self.table.setItem(row, 3, QTableWidgetItem(_format_time(entry.modified_time)))

    def selected_name(self) -> str | None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return None
        item = self.table.item(selected[0].row(), 0)
        return item.text() if item else None


def _format_time(value: datetime | None) -> str:
    return value.isoformat(timespec="seconds") if value else ""
