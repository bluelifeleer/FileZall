from datetime import UTC, datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableView, QTableWidget

from filezall_core.models import LocalFileEntry
from filezall_desktop.widgets import ICON_KEY_ROLE, FileEntryTableModel, FilePanel


def test_file_entry_table_model_handles_large_directory_without_widget_items(qtbot) -> None:
    entries = [
        LocalFileEntry(
            path=Path(f"C:/data/file-{index}.txt"),
            name=f"file-{index}.txt",
            is_dir=False,
            size_bytes=index,
            modified_time=datetime(2026, 6, 27, tzinfo=UTC),
        )
        for index in range(10_000)
    ]
    model = FileEntryTableModel()

    model.set_entries(entries)

    assert model.rowCount() == 10_001
    assert model.columnCount() == 4
    assert model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole) == ".."
    assert model.data(model.index(0, 0), Qt.ItemDataRole.UserRole) is True
    assert model.data(model.index(0, 0), ICON_KEY_ROLE) == "parent-dir"
    assert model.data(model.index(10_000, 0), Qt.ItemDataRole.DisplayRole) == "file-9999.txt"
    assert model.data(model.index(10_000, 1), Qt.ItemDataRole.DisplayRole) == "9999"
    assert model.data(model.index(10_000, 2), Qt.ItemDataRole.DisplayRole) == "File"
    assert model.data(model.index(10_000, 3), Qt.ItemDataRole.DisplayRole) == "2026-06-27 00:00:00 UTC+00:00"
    assert model.data(model.index(10_000, 0), ICON_KEY_ROLE) == "file-text"
    assert model.data(model.index(10_000, 1), ICON_KEY_ROLE) is None


def test_file_entry_table_model_adds_timezone_for_naive_modified_times(qtbot) -> None:
    model = FileEntryTableModel()
    model.set_entries(
        [
            LocalFileEntry(
                path=Path("C:/data/app.log"),
                name="app.log",
                is_dir=False,
                size_bytes=1,
                modified_time=datetime(2026, 6, 27, 8, 30, 15),
            )
        ]
    )

    value = model.data(model.index(1, 3), Qt.ItemDataRole.DisplayRole)

    assert value.startswith("2026-06-27 08:30:15 UTC")


def test_file_panel_keeps_virtual_entry_model_in_sync_for_large_directories(qtbot) -> None:
    entries = [
        LocalFileEntry(
            path=Path(f"C:/data/file-{index}.log"),
            name=f"file-{index}.log",
            is_dir=False,
            size_bytes=index,
            modified_time=datetime(2026, 6, 27, tzinfo=UTC),
        )
        for index in range(10_000)
    ]
    panel = FilePanel("Local Files", "Upload")
    qtbot.addWidget(panel)

    panel.set_entries(entries)

    assert panel.entry_model.rowCount() == 10_001
    assert panel.entry_model.data(
        panel.entry_model.index(10_000, 0),
        Qt.ItemDataRole.DisplayRole,
    ) == "file-9999.log"
    assert panel.entry_model.data(
        panel.entry_model.index(10_000, 0),
        ICON_KEY_ROLE,
    ) == "file-text"


def test_file_panel_uses_table_view_for_virtualized_file_rows(qtbot) -> None:
    panel = FilePanel("Local Files", "Upload")
    qtbot.addWidget(panel)

    assert isinstance(panel.table, QTableView)
    assert not isinstance(panel.table, QTableWidget)
    assert panel.table.model() is panel.entry_model


def test_file_panel_cancels_pending_batches_when_destroyed(qtbot) -> None:
    entries = [
        LocalFileEntry(
            path=Path(f"C:/data/file-{index}.log"),
            name=f"file-{index}.log",
            is_dir=False,
            size_bytes=index,
            modified_time=datetime(2026, 6, 27, tzinfo=UTC),
        )
        for index in range(5)
    ]
    panel = FilePanel("Local Files", "Upload")
    panel.large_directory_threshold = 1
    panel.entry_batch_size = 1

    panel.set_entries(entries)
    panel.deleteLater()
    qtbot.wait(10)
