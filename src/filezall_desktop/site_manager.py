from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from filezall_core.models import AuthMode, Protocol, SiteProfile
from filezall_core.site_import_export import export_sites, import_sites


class SiteManagerDialog(QDialog):
    sites_changed = Signal()

    def __init__(
        self,
        site_repository,
        parent=None,
        delete_confirmer=None,
        import_file_chooser=None,
        export_file_chooser=None,
        id_factory=None,
    ) -> None:
        super().__init__(parent)
        self._site_repository = site_repository
        self._delete_confirmer = delete_confirmer or _confirm_delete_site
        self._import_file_chooser = import_file_chooser or _choose_import_file
        self._export_file_chooser = export_file_chooser or _choose_export_file
        self._id_factory = id_factory or (lambda: uuid4().hex)
        self._sites: list[SiteProfile] = []
        self._visible_sites: list[SiteProfile] = []

        self.setWindowTitle("Site Manager")
        self.resize(860, 520)

        root = QVBoxLayout(self)
        filters = QHBoxLayout()
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Search sites")
        self.group_filter = QComboBox(self)
        filters.addWidget(self.search_edit)
        filters.addWidget(self.group_filter)
        root.addLayout(filters)

        self.table = QTableWidget(0, 6, self)
        self.table.setHorizontalHeaderLabels(["Name", "Group", "Host", "Port", "User", "Protocol"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self.table)

        actions = QHBoxLayout()
        self.new_button = QPushButton("New", self)
        self.edit_button = QPushButton("Edit", self)
        self.duplicate_button = QPushButton("Duplicate", self)
        self.delete_button = QPushButton("Delete", self)
        self.import_button = QPushButton("Import", self)
        self.export_button = QPushButton("Export", self)
        self.close_button = QPushButton("Close", self)
        for button in [
            self.new_button,
            self.edit_button,
            self.duplicate_button,
            self.delete_button,
            self.import_button,
            self.export_button,
            self.close_button,
        ]:
            actions.addWidget(button)
        root.addLayout(actions)

        self.search_edit.textChanged.connect(self._apply_filters)
        self.group_filter.currentTextChanged.connect(self._apply_filters)
        self.new_button.clicked.connect(self._handle_new)
        self.edit_button.clicked.connect(self._handle_edit)
        self.duplicate_button.clicked.connect(self._handle_duplicate)
        self.delete_button.clicked.connect(self._handle_delete)
        self.import_button.clicked.connect(self._handle_import)
        self.export_button.clicked.connect(self._handle_export)
        self.close_button.clicked.connect(self.close)

        self.reload()

    def reload(self) -> None:
        self._sites = self._site_repository.list() if self._site_repository is not None else []
        self._refresh_group_filter()
        self._apply_filters()

    def _refresh_group_filter(self) -> None:
        current = self.group_filter.currentText()
        groups = sorted({site.group_name for site in self._sites if site.group_name})
        self.group_filter.blockSignals(True)
        self.group_filter.clear()
        self.group_filter.addItem("All Groups")
        for group in groups:
            self.group_filter.addItem(group)
        index = self.group_filter.findText(current)
        self.group_filter.setCurrentIndex(index if index >= 0 else 0)
        self.group_filter.blockSignals(False)

    def _apply_filters(self) -> None:
        query = self.search_edit.text().strip().lower()
        group = self.group_filter.currentText()
        self._visible_sites = [
            site
            for site in self._sites
            if _matches_query(site, query)
            and (group in {"", "All Groups"} or site.group_name == group)
        ]
        self._render_table()

    def _render_table(self) -> None:
        self.table.setRowCount(len(self._visible_sites))
        for row, site in enumerate(self._visible_sites):
            values = [
                site.name,
                site.group_name,
                site.host,
                str(site.port),
                site.username,
                site.protocol.value.upper(),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(256, site.id)
                self.table.setItem(row, column, item)

    def _selected_site(self) -> SiteProfile | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._visible_sites):
            return None
        return self._visible_sites[row]

    def _handle_new(self) -> None:
        name, accepted = QInputDialog.getText(self, "New Site", "Site name")
        if not accepted or not name.strip():
            return
        site = SiteProfile(
            id=self._id_factory(),
            name=name.strip(),
            host="",
            port=22,
            protocol=Protocol.SFTP,
            username="",
            auth_mode=AuthMode.PASSWORD,
        )
        self._save_and_refresh(site)

    def _handle_edit(self) -> None:
        site = self._selected_site()
        if site is None:
            return
        name, accepted = QInputDialog.getText(self, "Edit Site", "Site name", text=site.name)
        if not accepted or not name.strip():
            return
        self._save_and_refresh(replace(site, name=name.strip()))

    def _handle_duplicate(self) -> None:
        site = self._selected_site()
        if site is None:
            return
        self._save_and_refresh(
            replace(
                site,
                id=self._id_factory(),
                name=f"{site.name} Copy",
                credential_ref=None,
                agent_token_ref=None,
            )
        )

    def _handle_delete(self) -> None:
        site = self._selected_site()
        if site is None:
            return
        if not self._delete_confirmer(self, site):
            return
        self._site_repository.delete(site.id)
        self.reload()
        self.sites_changed.emit()

    def _handle_import(self) -> None:
        selected = self._import_file_chooser(self)
        if not selected:
            return
        for site in import_sites(Path(selected)):
            self._site_repository.save(site)
        self.reload()
        self.sites_changed.emit()

    def _handle_export(self) -> None:
        selected = self._export_file_chooser(self)
        if not selected:
            return
        QMessageBox.information(
            self,
            "Export Sites",
            "Saved passwords and passphrases are not exported. They remain in the local credential manager.",
        )
        export_sites(self._sites, Path(selected))

    def _save_and_refresh(self, site: SiteProfile) -> None:
        self._site_repository.save(site)
        self.reload()
        self.sites_changed.emit()


def _matches_query(site: SiteProfile, query: str) -> bool:
    if not query:
        return True
    haystack = " ".join([site.name, site.group_name, site.host, site.username]).lower()
    return query in haystack


def _confirm_delete_site(parent, site: SiteProfile) -> bool:
    return (
        QMessageBox.question(
            parent,
            "Delete Site",
            f"Delete saved site '{site.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        == QMessageBox.StandardButton.Yes
    )


def _choose_import_file(parent) -> str:
    selected, _filter = QFileDialog.getOpenFileName(
        parent,
        "Import Sites",
        "",
        "JSON files (*.json);;All files (*)",
    )
    return selected


def _choose_export_file(parent) -> str:
    selected, _filter = QFileDialog.getSaveFileName(
        parent,
        "Export Sites",
        "filezall-sites.json",
        "JSON files (*.json);;All files (*)",
    )
    return selected
