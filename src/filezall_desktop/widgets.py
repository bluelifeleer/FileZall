from __future__ import annotations

from datetime import datetime
from pathlib import Path, PurePath

from PySide6.QtCore import (
    QAbstractTableModel,
    QItemSelectionModel,
    QModelIndex,
    QPoint,
    QRect,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
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
    QTableView,
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
    local_paths_dropped = Signal(object)

    def __init__(self, rows: int, columns: int, parent: QWidget | None = None) -> None:
        super().__init__(rows, columns, parent)
        self.hovered_row = -1
        self.full_row_hover_color = "#243244"
        self.full_row_selected_color = "#2563eb"
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setAcceptDrops(True)
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

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            paths = [
                Path(url.toLocalFile())
                for url in event.mimeData().urls()
                if url.isLocalFile()
            ]
            if paths:
                self.local_paths_dropped.emit(paths)
                event.acceptProposedAction()
                return
        super().dropEvent(event)

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


class VirtualTableHeaderItem:
    def __init__(self, text: str) -> None:
        self._text = text

    def text(self) -> str:
        return self._text


class VirtualTableItem:
    def __init__(self, model: QAbstractTableModel, row: int, column: int) -> None:
        self._model = model
        self._index = model.index(row, column)

    def text(self) -> str:
        value = self._model.data(self._index, Qt.ItemDataRole.DisplayRole)
        return "" if value is None else str(value)

    def data(self, role: int):
        return self._model.data(self._index, role)

    def icon(self) -> QIcon:
        value = self._model.data(self._index, Qt.ItemDataRole.DecorationRole)
        return value if isinstance(value, QIcon) else QIcon()


class HoverRowTableView(QTableView):
    cellClicked = Signal(int, int)
    cellDoubleClicked = Signal(int, int)
    local_paths_dropped = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.hovered_row = -1
        self.full_row_hover_color = "#243244"
        self.full_row_selected_color = "#2563eb"
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setShowGrid(False)
        self.clicked.connect(lambda index: self.cellClicked.emit(index.row(), index.column()))
        self.doubleClicked.connect(
            lambda index: self.cellDoubleClicked.emit(index.row(), index.column())
        )

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

    def rowCount(self) -> int:
        model = self.model()
        return model.rowCount() if model else 0

    def columnCount(self) -> int:
        model = self.model()
        return model.columnCount() if model else 0

    def item(self, row: int, column: int) -> VirtualTableItem | None:
        model = self.model()
        if not model or row < 0 or column < 0:
            return None
        if row >= model.rowCount() or column >= model.columnCount():
            return None
        return VirtualTableItem(model, row, column)

    def horizontalHeaderItem(self, section: int) -> VirtualTableHeaderItem:
        model = self.model()
        text = ""
        if model:
            value = model.headerData(
                section,
                Qt.Orientation.Horizontal,
                Qt.ItemDataRole.DisplayRole,
            )
            text = "" if value is None else str(value)
        return VirtualTableHeaderItem(text)

    def setCurrentCell(self, row: int, column: int) -> None:
        model = self.model()
        if not model:
            return
        self.setCurrentIndex(model.index(row, column))

    def currentRow(self) -> int:
        index = self.currentIndex()
        return index.row() if index.isValid() else -1

    def setRangeSelected(self, selection_range, select: bool) -> None:
        model = self.model()
        selection_model = self.selectionModel()
        if not model or not selection_model:
            return
        flags = (
            QItemSelectionModel.SelectionFlag.Select
            if select
            else QItemSelectionModel.SelectionFlag.Deselect
        ) | QItemSelectionModel.SelectionFlag.Rows
        for row in range(selection_range.topRow(), selection_range.bottomRow() + 1):
            selection_model.select(model.index(row, 0), flags)

    def mouseMoveEvent(self, event) -> None:
        index = self.indexAt(event.position().toPoint())
        self.set_hovered_row(index.row() if index.isValid() else -1)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self.set_hovered_row(-1)
        super().leaveEvent(event)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dropEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            paths = [
                Path(url.toLocalFile())
                for url in event.mimeData().urls()
                if url.isLocalFile()
            ]
            if paths:
                self.local_paths_dropped.emit(paths)
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        for row, color in self._active_row_colors():
            first_rect = self.visualRect(self.model().index(row, 0))
            last_rect = self.visualRect(self.model().index(row, self.columnCount() - 1))
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
                painter.fillRect(trailing_rect, QColor(color))
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
        if hasattr(table, "hovered_row") and (
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


class DirectoryHistoryComboBox(QComboBox):
    history_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None, max_history: int = 20) -> None:
        super().__init__(parent)
        self._max_history = max_history
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.returnPressed = self.lineEdit().returnPressed
        self.activated.connect(self._handle_activated)

    def text(self) -> str:
        return self.currentText()

    def setText(self, text: str) -> None:
        self.setEditText(text)

    def add_history(self, path: str) -> None:
        value = path.strip()
        if not value:
            return
        existing_index = self.findText(value)
        if existing_index >= 0:
            self.removeItem(existing_index)
        self.insertItem(0, value)
        while self.count() > self._max_history:
            self.removeItem(self.count() - 1)
        self.setCurrentIndex(0)
        self.setEditText(value)

    def _handle_activated(self, index: int) -> None:
        text = self.itemText(index) if index >= 0 else self.currentText()
        if text:
            self.history_selected.emit(text)


class FileEntryTableModel(QAbstractTableModel):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        headers: list[str] | None = None,
        parent_label: str = "Parent Directory",
        directory_label: str = "Directory",
        file_label: str = "File",
    ) -> None:
        super().__init__(parent)
        self._headers = headers or ["Name", "Size", "Type", "Modified"]
        self._parent_label = parent_label
        self._directory_label = directory_label
        self._file_label = file_label
        self._entries = []
        self._placeholder_text: str | None = None

    def set_texts(
        self,
        *,
        headers: list[str],
        parent_label: str,
        directory_label: str,
        file_label: str,
    ) -> None:
        self.beginResetModel()
        self._headers = headers
        self._parent_label = parent_label
        self._directory_label = directory_label
        self._file_label = file_label
        self.endResetModel()

    def set_entries(self, entries) -> None:
        self.beginResetModel()
        self._placeholder_text = None
        self._entries = list(entries)
        self.endResetModel()

    def set_placeholder(self, text: str) -> None:
        self.beginResetModel()
        self._placeholder_text = text
        self._entries = []
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        if self._placeholder_text is not None:
            return 1
        return len(self._entries) + 1

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return 4

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        column = index.column()
        if self._placeholder_text is not None:
            return self._placeholder_data(column, role)
        if row == 0:
            return self._parent_data(column, role)
        entry = self._entry_at(row)
        if entry is None:
            return None
        return self._entry_data(entry, column, role)

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

    def _placeholder_data(self, column: int, role: int):
        if role == Qt.ItemDataRole.DisplayRole:
            return self._placeholder_text if column == 0 else ""
        if role == Qt.ItemDataRole.UserRole:
            return False
        if role == _ROW_KIND_ROLE:
            return "placeholder"
        if role == ICON_KEY_ROLE and column == 0:
            return _entry_icon_key(self._placeholder_text or "", False, "placeholder")
        if role == Qt.ItemDataRole.DecorationRole and column == 0:
            return _entry_icon(self._placeholder_text or "", False, "placeholder")
        return None

    def _entry_at(self, row: int):
        index = row - 1
        if 0 <= index < len(self._entries):
            return self._entries[index]
        return None

    def _parent_data(self, column: int, role: int):
        if role == Qt.ItemDataRole.DisplayRole:
            return ["..", "", self._parent_label, ""][column] if 0 <= column < 4 else None
        if role == Qt.ItemDataRole.UserRole:
            return True
        if role == _ROW_KIND_ROLE:
            return "parent"
        if role == ICON_KEY_ROLE and column == 0:
            return "parent-dir"
        if role == Qt.ItemDataRole.DecorationRole and column == 0:
            return _entry_icon("..", True, "parent")
        return None

    def _entry_data(self, entry, column: int, role: int):
        if role == Qt.ItemDataRole.DisplayRole:
            if column == 0:
                return entry.name
            if column == 1:
                return str(entry.size_bytes)
            if column == 2:
                return self._directory_label if entry.is_dir else self._file_label
            if column == 3:
                return _format_time(entry.modified_time)
        if role == Qt.ItemDataRole.UserRole:
            return entry.is_dir
        if role == _ROW_KIND_ROLE:
            return "entry"
        if role == ICON_KEY_ROLE and column == 0:
            return _entry_icon_key(entry.name, entry.is_dir, "entry")
        if role == Qt.ItemDataRole.DecorationRole and column == 0:
            return _entry_icon(entry.name, entry.is_dir, "entry")
        return None


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
        self.large_directory_threshold = 500
        self.entry_batch_size = 200
        self.is_loading_entries = False
        self._entry_batch_generation = 0
        self._pending_entries = []
        self._pending_entry_index = 0
        self._entry_batch_timer = QTimer(self)
        self._entry_batch_timer.setSingleShot(True)
        self._entry_batch_timer.timeout.connect(self._append_scheduled_entry_batch)
        self.entry_model = FileEntryTableModel(
            self,
            parent_label=self._parent_label,
            directory_label=self._directory_label,
            file_label=self._file_label,
        )
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self.title = QLabel(title, self)
        self.path_edit = DirectoryHistoryComboBox(self)
        self.path_button = QToolButton(self)
        self.path_button.setObjectName("pathButton")
        self.path_button.setText(path_button_text)
        self.path_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.path_button.setFixedWidth(32)
        self.path_button.setToolTip("Choose or enter directory")
        self.refresh_button = QPushButton("Refresh", self)
        self.action_button = QPushButton(action_label, self)
        self.table = HoverRowTableView(self)
        self.table.setModel(self.entry_model)
        self.table.setIconSize(QSize(22, 22))
        self.table.setItemDelegate(HoverRowDelegate(self.table))
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header_view.resizeSection(0, 220)
        header_view.resizeSection(1, 90)
        header_view.resizeSection(2, 110)
        header_view.setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self._build_context_menu()
        self.load_progress_label = QLabel("", self)

        header.addWidget(self.title)
        header.addWidget(self.path_edit)
        header.addWidget(self.path_button)
        header.addWidget(self.refresh_button)
        header.addWidget(self.action_button)
        layout.addLayout(header)
        layout.addWidget(self.table)
        layout.addWidget(self.load_progress_label)

    def _build_context_menu(self) -> None:
        self.context_menu = QMenu(self)
        self.refresh_action = QAction("Refresh", self)
        self.delete_action = QAction("Delete", self)
        self.rename_action = QAction("Rename", self)
        self.copy_path_action = QAction("Copy Path", self)
        self.queue_action = QAction("Add to Queue", self)
        self.transfer_action = QAction(self._transfer_action_label, self)
        self.create_dir_action = QAction("Create Directory", self)
        self.create_file_action = QAction("Create File", self)
        for action in [
            self.refresh_action,
            self.delete_action,
            self.rename_action,
            self.copy_path_action,
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
        rename_label: str,
        copy_path_label: str,
        queue_label: str,
        create_dir_label: str,
        create_file_label: str,
    ) -> None:
        self.title.setText(title)
        self.refresh_button.setText(refresh_label)
        self.action_button.setText(action_label)
        self.path_button.setText(path_button_text)
        self.path_button.setToolTip(choose_directory_tooltip)
        self._transfer_action_label = transfer_label
        self._parent_label = parent_label
        self._directory_label = directory_label
        self._file_label = file_label
        self.entry_model.set_texts(
            headers=headers,
            parent_label=parent_label,
            directory_label=directory_label,
            file_label=file_label,
        )
        self.transfer_action.setText(transfer_label)
        self.delete_action.setText(delete_label)
        self.rename_action.setText(rename_label)
        self.copy_path_action.setText(copy_path_label)
        self.queue_action.setText(queue_label)
        self.create_dir_action.setText(create_dir_label)
        self.create_file_action.setText(create_file_label)

    def _show_context_menu(self, position) -> None:
        self.context_menu.exec(self.table.viewport().mapToGlobal(position))

    def set_placeholder_row(self, text: str) -> None:
        self._cancel_pending_entry_batches()
        self.entry_model.set_placeholder(text)
        self.clear_selection()
        self.load_progress_label.setText("")

    def set_entries(self, entries) -> None:
        entries = list(entries)
        self._cancel_pending_entry_batches()
        self.entry_model.set_entries(entries)
        self.clear_selection()
        self.load_progress_label.setText(f"{len(entries)} items" if entries else "")
        self.table.viewport().update()

    def _start_batched_entries(self, entries: list) -> None:
        self.is_loading_entries = True
        self._pending_entries = entries
        self._pending_entry_index = 0
        generation = self._entry_batch_generation
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(1)
            self._set_row(0, "..", "", self._parent_label, "", is_dir=True, row_kind="parent")
            self.clear_selection()
        finally:
            self.table.setUpdatesEnabled(True)
        self._append_entry_batch(generation)

    def _append_entry_batch(self, generation: int) -> None:
        if generation != self._entry_batch_generation:
            return
        entries = self._pending_entries
        start = self._pending_entry_index
        end = min(start + self.entry_batch_size, len(entries))
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(end + 1)
            for row, entry in enumerate(entries[start:end], start=start + 1):
                self.table.setItem(row, 0, _entry_item(entry.name, entry.is_dir, show_icon=True))
                self.table.setItem(row, 1, _entry_item(str(entry.size_bytes), entry.is_dir))
                self.table.setItem(
                    row,
                    2,
                    _entry_item(
                        self._directory_label if entry.is_dir else self._file_label,
                        entry.is_dir,
                    ),
                )
                self.table.setItem(
                    row,
                    3,
                    _entry_item(_format_time(entry.modified_time), entry.is_dir),
                )
        finally:
            self.table.setUpdatesEnabled(True)
        self._pending_entry_index = end
        if end < len(entries):
            self.load_progress_label.setText(f"Loading {end}/{len(entries)} items...")
            self.table.viewport().update()
            self._entry_batch_timer.start(0)
            return
        self.is_loading_entries = False
        self._pending_entries = []
        self.load_progress_label.setText(f"{len(entries)} items")
        self.table.viewport().update()

    def _append_scheduled_entry_batch(self) -> None:
        self._append_entry_batch(self._entry_batch_generation)

    def _cancel_pending_entry_batches(self) -> None:
        if hasattr(self, "_entry_batch_timer"):
            self._entry_batch_timer.stop()
        self._entry_batch_generation += 1
        self.is_loading_entries = False
        self._pending_entries = []
        self._pending_entry_index = 0

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
        self.table.setCurrentIndex(QModelIndex())
        self.table.set_hovered_row(-1)

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
        return None


def _format_time(value: datetime | None) -> str:
    return value.isoformat(timespec="seconds") if value else ""


_ROW_KIND_ROLE = Qt.ItemDataRole.UserRole + 1
ICON_KEY_ROLE = Qt.ItemDataRole.UserRole + 2


def _entry_item(
    text: str,
    is_dir: bool,
    row_kind: str = "entry",
    *,
    show_icon: bool = False,
) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    if show_icon and text:
        icon_key = _entry_icon_key(text, is_dir, row_kind)
        item.setData(ICON_KEY_ROLE, icon_key)
        icon = _entry_icon(text, is_dir, row_kind)
        if not icon.isNull():
            item.setIcon(icon)
    item.setData(Qt.ItemDataRole.UserRole, is_dir)
    item.setData(_ROW_KIND_ROLE, row_kind)
    return item


_ICON_CACHE: dict[str, QIcon] = {}


def _entry_icon(text: str, is_dir: bool, row_kind: str) -> QIcon:
    key = _entry_icon_key(text, is_dir, row_kind)
    if is_dir:
        if key not in _ICON_CACHE:
            _ICON_CACHE[key] = _paint_folder_icon(parent=row_kind == "parent")
        return _ICON_CACHE[key]
    suffix = PurePath(text).suffix.lower().lstrip(".")
    label = _suffix_label(suffix)
    if key not in _ICON_CACHE:
        _ICON_CACHE[key] = _paint_icon(label, _suffix_color(suffix))
    return _ICON_CACHE[key]


def _entry_icon_key(text: str, is_dir: bool, row_kind: str) -> str:
    if is_dir:
        return "parent-dir" if row_kind == "parent" else "dir"
    suffix = PurePath(text).suffix.lower().lstrip(".")
    if suffix in {"py", "js", "ts", "css", "go", "rs", "sh"}:
        return f"file-code-{suffix}"
    if suffix in {"png", "jpg", "jpeg", "gif", "webp", "svg"}:
        return "file-image"
    if suffix in {"zip", "rar", "7z", "tar", "gz"}:
        return "file-archive"
    if suffix in {"json", "yaml", "yml", "toml", "xml", "ini", "conf", "env"}:
        return "file-config"
    if suffix in {"md", "txt", "log"}:
        return "file-text"
    return "file-unknown"


def _suffix_label(suffix: str) -> str:
    if suffix in {"py", "js", "ts", "css", "go", "rs", "sh"}:
        return suffix.upper()
    if suffix in {"png", "jpg", "jpeg", "gif", "webp", "svg"}:
        return "IMG"
    if suffix in {"zip", "rar", "7z", "tar", "gz"}:
        return "ZIP"
    if suffix in {"json", "yaml", "yml", "toml", "xml"}:
        return "CFG"
    if suffix in {"md", "txt", "log"}:
        return "TXT"
    return "FILE"


def _suffix_color(suffix: str) -> str:
    if suffix in {"py", "go", "rs", "sh"}:
        return "#2563eb"
    if suffix in {"js", "ts", "css"}:
        return "#ca8a04"
    if suffix in {"png", "jpg", "jpeg", "gif", "webp", "svg"}:
        return "#16a34a"
    if suffix in {"zip", "rar", "7z", "tar", "gz"}:
        return "#9333ea"
    if suffix in {"json", "yaml", "yml", "toml", "xml"}:
        return "#0891b2"
    return "#64748b"


def _paint_folder_icon(*, parent: bool = False) -> QIcon:
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#f59e0b" if parent else "#3b82f6"))
    painter.drawRoundedRect(3, 10, 26, 17, 4, 4)
    painter.setBrush(QColor("#fbbf24" if parent else "#60a5fa"))
    painter.drawRoundedRect(5, 6, 12, 8, 3, 3)
    painter.setBrush(QColor(255, 255, 255, 46))
    painter.drawRoundedRect(6, 13, 20, 5, 2, 2)
    if parent:
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawLine(17, 19, 12, 19)
        painter.drawLine(12, 19, 15, 16)
        painter.drawLine(12, 19, 15, 22)
    painter.end()
    return QIcon(pixmap)


def _paint_icon(label: str, color: str = "#2563eb") -> QIcon:
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(color), 1))
    painter.setBrush(QColor("#ffffff"))
    painter.drawRoundedRect(6, 3, 20, 26, 4, 4)
    painter.setBrush(QColor(color))
    painter.drawRoundedRect(6, 18, 20, 11, 3, 3)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color).lighter(150))
    painter.drawPolygon([QPoint(21, 3), QPoint(26, 8), QPoint(21, 8)])
    painter.setPen(QPen(QColor("#cbd5e1"), 1))
    painter.drawLine(10, 10, 21, 10)
    painter.drawLine(10, 14, 21, 14)
    painter.setPen(QColor("#ffffff"))
    font = painter.font()
    font.setPointSize(6 if len(label) > 2 else 7)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(QRect(6, 18, 20, 10), Qt.AlignmentFlag.AlignCenter, label[:3])
    painter.end()
    return QIcon(pixmap)
