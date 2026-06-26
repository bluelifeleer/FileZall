from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from filezall_core.log_service import LogRecord


LOG_CATEGORIES = ["all", "connection", "transfer", "agent", "resource", "error"]


class LogViewer(QWidget):
    def __init__(
        self,
        parent=None,
        *,
        export_logs_callback: Callable[[], None] | None = None,
        export_diagnostics_callback: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._records: list[LogRecord] = []
        self._category_filter = "all"
        self._export_logs_callback = export_logs_callback
        self._export_diagnostics_callback = export_diagnostics_callback

        layout = QVBoxLayout(self)
        actions = QHBoxLayout()
        self.category_filter = QComboBox(self)
        self.category_filter.addItems(LOG_CATEGORIES)
        self.copy_error_button = QPushButton("Copy Error", self)
        self.export_logs_button = QPushButton("Export Logs", self)
        self.export_diagnostics_button = QPushButton("Export Diagnostics", self)
        actions.addWidget(self.category_filter)
        actions.addWidget(self.copy_error_button)
        actions.addStretch(1)
        actions.addWidget(self.export_logs_button)
        actions.addWidget(self.export_diagnostics_button)
        layout.addLayout(actions)

        self.record_list = QListWidget(self)
        layout.addWidget(self.record_list)

        self.text_view = QPlainTextEdit(self)
        self.text_view.setReadOnly(True)
        self.text_view.setMaximumBlockCount(1000)
        layout.addWidget(self.text_view)

        self.category_filter.currentTextChanged.connect(self.set_category_filter)
        self.copy_error_button.clicked.connect(self.copy_selected_error)
        self.export_logs_button.clicked.connect(self._export_logs)
        self.export_diagnostics_button.clicked.connect(self._export_diagnostics)

    def add_record(self, record: LogRecord) -> None:
        self._records.append(record)
        self._refresh()

    def set_category_filter(self, category: str) -> None:
        self._category_filter = category if category in LOG_CATEGORIES else "all"
        if self.category_filter.currentText() != self._category_filter:
            self.category_filter.setCurrentText(self._category_filter)
            return
        self._refresh()

    def copy_selected_error(self) -> None:
        item = self.record_list.currentItem()
        if item is None:
            return
        record = item.data(256)
        if isinstance(record, LogRecord) and record.level == "error":
            self.clipboard().setText(record.message)

    def toPlainText(self) -> str:
        return self.text_view.toPlainText()

    def appendPlainText(self, text: str) -> None:
        self.text_view.appendPlainText(text)

    def clipboard(self):
        return QApplication.clipboard()

    def _filtered_records(self) -> list[LogRecord]:
        if self._category_filter == "all":
            return list(self._records)
        return [record for record in self._records if record.category == self._category_filter]

    def _refresh(self) -> None:
        records = self._filtered_records()
        self.record_list.clear()
        self.text_view.setPlainText("\n".join(record.format() for record in records))
        for record in records:
            item = QListWidgetItem(record.format())
            item.setData(256, record)
            self.record_list.addItem(item)

    def _export_logs(self) -> None:
        if self._export_logs_callback is not None:
            self._export_logs_callback()

    def _export_diagnostics(self) -> None:
        if self._export_diagnostics_callback is not None:
            self._export_diagnostics_callback()
