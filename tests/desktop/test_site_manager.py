from pathlib import Path, PurePosixPath

from PySide6.QtCore import Qt

from filezall_core.models import AuthMode, Protocol, SiteProfile
from filezall_desktop.site_manager import SiteManagerDialog


class FakeSiteRepository:
    def __init__(self, sites: list[SiteProfile]) -> None:
        self.sites = list(sites)
        self.saved = []
        self.deleted = []

    def list(self) -> list[SiteProfile]:
        return list(self.sites)

    def save(self, site: SiteProfile) -> None:
        self.saved.append(site)
        self.sites = [existing for existing in self.sites if existing.id != site.id]
        self.sites.append(site)

    def delete(self, site_id: str) -> None:
        self.deleted.append(site_id)
        self.sites = [site for site in self.sites if site.id != site_id]


def _site(site_id: str, name: str, group_name: str = "") -> SiteProfile:
    return SiteProfile(
        id=site_id,
        name=name,
        host=f"{site_id}.example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
        default_local_path=Path("C:/work"),
        default_remote_path=PurePosixPath("/var/www"),
        group_name=group_name,
    )


def test_site_manager_renders_controls_and_filters_sites(qtbot) -> None:
    repository = FakeSiteRepository(
        [
            _site("prod", "Production API", "Production"),
            _site("stage", "Staging API", "Staging"),
        ]
    )
    dialog = SiteManagerDialog(repository)
    qtbot.addWidget(dialog)

    assert dialog.search_edit.placeholderText() == "Search sites"
    assert dialog.group_filter.count() == 3
    assert dialog.new_button.text() == "New"
    assert dialog.edit_button.text() == "Edit"
    assert dialog.duplicate_button.text() == "Duplicate"
    assert dialog.delete_button.text() == "Delete"
    assert dialog.import_button.text() == "Import"
    assert dialog.export_button.text() == "Export"
    assert dialog.close_button.text() == "Close"
    assert dialog.table.rowCount() == 2

    dialog.search_edit.setText("staging")

    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 0).text() == "Staging API"

    dialog.search_edit.clear()
    dialog.group_filter.setCurrentText("Production")

    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 0).text() == "Production API"


def test_site_manager_duplicate_and_delete_emit_changes(qtbot) -> None:
    repository = FakeSiteRepository([_site("prod", "Production API", "Production")])
    dialog = SiteManagerDialog(
        repository,
        delete_confirmer=lambda _parent, _site: True,
        id_factory=lambda: "copy-id",
    )
    qtbot.addWidget(dialog)
    changes = []
    dialog.sites_changed.connect(lambda: changes.append("changed"))

    dialog.table.selectRow(0)
    qtbot.mouseClick(dialog.duplicate_button, Qt.MouseButton.LeftButton)

    assert repository.saved[-1].id == "copy-id"
    assert repository.saved[-1].name == "Production API Copy"
    assert changes == ["changed"]

    copy_row = next(
        row
        for row in range(dialog.table.rowCount())
        if dialog.table.item(row, 0).text() == "Production API Copy"
    )
    dialog.table.selectRow(copy_row)
    qtbot.mouseClick(dialog.delete_button, Qt.MouseButton.LeftButton)

    assert repository.deleted == ["copy-id"]
    assert changes == ["changed", "changed"]
