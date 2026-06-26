import sqlite3

from filezall_desktop.app import create_main_window
from filezall_desktop.i18n import SYSTEM_LANGUAGE, t


def test_create_main_window_initializes_database(monkeypatch, qtbot, tmp_path) -> None:
    monkeypatch.setenv("FILEZALL_HOME", str(tmp_path))

    window = create_main_window()
    qtbot.addWidget(window)

    database = tmp_path / "filezall.sqlite3"
    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type = 'table'"
            )
        }

    assert "site_profiles" in tables
    assert (tmp_path / "logs" / "filezall-runtime.log").exists()
    assert window.connection_bar.site_selector.itemText(0) == t(SYSTEM_LANGUAGE, "site.quick")
    assert window.controller._agent_install_service is not None
