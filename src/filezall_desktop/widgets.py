from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QAction, QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
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
        self.auth_mode_selector.addItem("Password", "password")
        self.auth_mode_selector.addItem("SSH Key", "ssh_key")
        self.secret_edit = QLineEdit(self)
        self.secret_edit.setPlaceholderText("Password / passphrase")
        self.secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.ssh_key_path_edit = QLineEdit(self)
        self.ssh_key_path_edit.setPlaceholderText("SSH key path")
        self.protocol_selector = QComboBox(self)
        self.protocol_selector.addItems(["SFTP", "FTP", "FTPS"])
        self.connect_button = QPushButton("Connect", self)
        self.disconnect_button = QPushButton("Disconnect", self)
        self.install_agent_button = QPushButton("Install Agent", self)

        self.site_label = QLabel("Site", self)
        layout.addWidget(self.site_label)
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
        layout.addWidget(self.install_agent_button)


class HoverRowTableWidget(QTableWidget):
    def __init__(self, rows: int, columns: int, parent: QWidget | None = None) -> None:
        super().__init__(rows, columns, parent)
        self.hovered_row = -1
        self.full_row_hover_color = "#243244"
        self.full_row_selected_color = "#2563eb"
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setShowGrid(False)

    def set_full_row_hover_color(self, color: str) -> None:
        self.full_row_hover_color = color
        self.viewport().update()

    def set_full_row_selected_color(self, color: str) -> None:
        self.full_row_selected_color = color
        self.viewport().update()

    def set_hovered_row(self, row: int) -> None:
        if row == self.hovered_row:
            return
        self.hovered_row = row
        self.viewport().update()

    def mouseMoveEvent(self, event) -> None:
        index = self.indexAt(event.position().toPoint())
        self.set_hovered_row(index.row() if index.isValid() else -1)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self.set_hovered_row(-1)
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        for row, color in self._active_row_colors():
            first_rect = self.visualRect(self.model().index(row, 0))
            last_rect = self.visualRect(
                self.model().index(row, self.columnCount() - 1)
            )
            if first_rect.isValid() and last_rect.isValid():
                left = last_rect.right() + 1
                if left >= self.viewport().width():
                    continue
                painter = QPainter(self.viewport())
                trailing_rect = QRect(
                    left,
                    first_rect.top(),
                    self.viewport().width() - left,
                    first_rect.height(),
                )
                painter.fillRect(
                    trailing_rect,
                    QColor(color),
                )
                painter.end()

    def _active_row_colors(self) -> list[tuple[int, str]]:
        rows: list[tuple[int, str]] = []
        selection_model = self.selectionModel()
        if selection_model:
            rows.extend(
                (index.row(), self.full_row_selected_color)
                for index in selection_model.selectedRows()
            )
        if self.hovered_row >= 0 and not any(row == self.hovered_row for row, _ in rows):
            rows.append((self.hovered_row, self.full_row_hover_color))
        return rows


class HoverRowDelegate(QStyledItemDelegate):
    uses_full_row_activity = True
    clears_cell_selection_paint = True

    def paint(self, painter, option, index) -> None:
        table = self.parent()
        if isinstance(table, HoverRowTableWidget) and (
            index.row() == table.hovered_row
            or option.state & QStyle.StateFlag.State_Selected
        ):
            option = QStyleOptionViewItem(option)
            self.initStyleOption(option, index)
            painter.save()
            painter.fillRect(
                option.rect,
                QColor(
                    table.full_row_hover_color
                    if index.row() == table.hovered_row
                    else table.full_row_selected_color
                ),
            )
            painter.restore()
            option.state &= ~QStyle.StateFlag.State_Selected
            option.state &= ~QStyle.StateFlag.State_HasFocus
            option.showDecorationSelected = False
        super().paint(painter, option, index)


class FilePanel(QWidget):
    def __init__(
        self,
        title: str,
        action_label: str,
        path_button_text: str = "...",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._transfer_action_label = action_label
        self._parent_label = "Parent Directory"
        self._directory_label = "Directory"
        self._file_label = "File"
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self.title = QLabel(title, self)
        self.path_edit = QLineEdit(self)
        self.path_button = QToolButton(self)
        self.path_button.setText(path_button_text)
        self.path_button.setMaximumWidth(28)
        self.path_button.setToolTip("Choose or enter directory")
        self.refresh_button = QPushButton("Refresh", self)
        self.action_button = QPushButton(action_label, self)
        self.table = HoverRowTableWidget(0, 4, self)
        self.table.setItemDelegate(HoverRowDelegate(self.table))
        self.table.setHorizontalHeaderLabels(["Name", "Size", "Type", "Modified"])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self._build_context_menu()

        header.addWidget(self.title)
        header.addWidget(self.path_edit)
        header.addWidget(self.path_button)
        header.addWidget(self.refresh_button)
        header.addWidget(self.action_button)
        layout.addLayout(header)
        layout.addWidget(self.table)

    def _build_context_menu(self) -> None:
        self.context_menu = QMenu(self)
        self.refresh_action = QAction("Refresh", self)
        self.delete_action = QAction("Delete", self)
        self.queue_action = QAction("Add to Queue", self)
        self.transfer_action = QAction(self._transfer_action_label, self)
        self.create_dir_action = QAction("Create Directory", self)
        self.create_file_action = QAction("Create File", self)
        for action in [
            self.refresh_action,
            self.delete_action,
            self.queue_action,
            self.transfer_action,
            self.create_dir_action,
            self.create_file_action,
        ]:
            self.context_menu.addAction(action)

    def set_texts(
        self,
        *,
        title: str,
        refresh_label: str,
        action_label: str,
        transfer_label: str,
        path_button_text: str,
        choose_directory_tooltip: str,
        headers: list[str],
        parent_label: str,
        directory_label: str,
        file_label: str,
        delete_label: str,
        queue_label: str,
        create_dir_label: str,
        create_file_label: str,
    ) -> None:
        self.title.setText(title)
        self.refresh_button.setText(refresh_label)
        self.action_button.setText(action_label)
        self.path_button.setText(path_button_text)
        self.path_button.setToolTip(choose_directory_tooltip)
        self.table.setHorizontalHeaderLabels(headers)
        self._transfer_action_label = transfer_label
        self._parent_label = parent_label
        self._directory_label = directory_label
        self._file_label = file_label
        self.transfer_action.setText(transfer_label)
        self.delete_action.setText(delete_label)
        self.queue_action.setText(queue_label)
        self.create_dir_action.setText(create_dir_label)
        self.create_file_action.setText(create_file_label)

    def _show_context_menu(self, position) -> None:
        self.context_menu.exec(self.table.viewport().mapToGlobal(position))

    def set_placeholder_row(self, text: str) -> None:
        self.table.setRowCount(1)
        self.table.setItem(0, 0, _entry_item(text, False))
        self.table.setItem(0, 1, _entry_item("", False))
        self.table.setItem(0, 2, _entry_item("", False))
        self.table.setItem(0, 3, _entry_item("", False))

    def set_entries(self, entries) -> None:
        self.table.setRowCount(len(entries) + 1)
        self._set_row(0, "..", "", self._parent_label, "", is_dir=True, row_kind="parent")
        for row, entry in enumerate(entries, start=1):
            self.table.setItem(row, 0, _entry_item(entry.name, entry.is_dir))
            self.table.setItem(row, 1, _entry_item(str(entry.size_bytes), entry.is_dir))
            self.table.setItem(
                row,
                2,
                _entry_item(
                    self._directory_label if entry.is_dir else self._file_label,
                    entry.is_dir,
                ),
            )
            self.table.setItem(row, 3, _entry_item(_format_time(entry.modified_time), entry.is_dir))
        self.clear_selection()

    def selected_name(self) -> str | None:
        names = self.selected_names()
        return names[0] if names else None

    def selected_names(self) -> list[str]:
        return [
            name
            for row in self.selected_rows()
            if not self.is_parent_at(row)
            for name in [self.name_at(row)]
            if name
        ]

    def selected_rows(self) -> list[int]:
        selected = self.table.selectionModel().selectedRows()
        return sorted(index.row() for index in selected)

    def selected_is_dir(self) -> bool:
        rows = [row for row in self.selected_rows() if not self.is_parent_at(row)]
        if not rows:
            return False
        return self.is_dir_at(rows[0])

    def name_at(self, row: int) -> str | None:
        item = self.table.item(row, 0)
        return item.text() if item else None

    def is_dir_at(self, row: int) -> bool:
        item = self.table.item(row, 0)
        return bool(item.data(Qt.ItemDataRole.UserRole)) if item else False

    def is_parent_at(self, row: int) -> bool:
        item = self.table.item(row, 0)
        return item.data(_ROW_KIND_ROLE) == "parent" if item else False

    def clear_selection(self) -> None:
        self.table.clearSelection()

    def _set_row(
        self,
        row: int,
        name: str,
        size: str,
        kind: str,
        modified: str,
        *,
        is_dir: bool,
        row_kind: str,
    ) -> None:
        self.table.setItem(row, 0, _entry_item(name, is_dir, row_kind))
        self.table.setItem(row, 1, _entry_item(size, is_dir, row_kind))
        self.table.setItem(row, 2, _entry_item(kind, is_dir, row_kind))
        self.table.setItem(row, 3, _entry_item(modified, is_dir, row_kind))


def _format_time(value: datetime | None) -> str:
    return value.isoformat(timespec="seconds") if value else ""


_ROW_KIND_ROLE = Qt.ItemDataRole.UserRole + 1


def _entry_item(text: str, is_dir: bool, row_kind: str = "entry") -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setData(Qt.ItemDataRole.UserRole, is_dir)
    item.setData(_ROW_KIND_ROLE, row_kind)
    return item
