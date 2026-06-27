from PySide6.QtCore import Qt

from filezall_core.log_service import TransferLogService
from filezall_desktop.log_viewer import LogViewer


def test_log_viewer_filters_categories_and_copies_errors(qtbot) -> None:
    service = TransferLogService()
    viewer = LogViewer()
    qtbot.addWidget(viewer)

    viewer.add_record(service.append_connection("Connected to Production"))
    viewer.add_record(service.append_transfer("Uploaded app.txt"))
    viewer.add_record(service.append_error("Connection failed: bad password"))

    assert "Connected to Production" in viewer.toPlainText()
    assert "Uploaded app.txt" in viewer.toPlainText()

    viewer.set_category_filter("error")

    assert "Connection failed: bad password" in viewer.toPlainText()
    assert "Uploaded app.txt" not in viewer.toPlainText()
    viewer.record_list.setCurrentRow(0)
    viewer.copy_selected_error()

    assert (
        "Connection failed: bad password" in viewer.clipboard().text()
        or "Connection failed: bad password" in viewer.last_copied_text
    )


def test_log_viewer_exposes_export_actions(qtbot) -> None:
    triggered: list[str] = []
    viewer = LogViewer(
        export_logs_callback=lambda: triggered.append("logs"),
        export_diagnostics_callback=lambda: triggered.append("diagnostics"),
    )
    qtbot.addWidget(viewer)

    qtbot.mouseClick(viewer.export_logs_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(viewer.export_diagnostics_button, Qt.MouseButton.LeftButton)

    assert triggered == ["logs", "diagnostics"]


def test_log_viewer_uses_one_visible_log_display(qtbot) -> None:
    viewer = LogViewer()
    qtbot.addWidget(viewer)

    assert viewer.record_list.isVisibleTo(viewer)
    assert not hasattr(viewer, "text_view")
