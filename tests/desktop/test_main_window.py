from filezall_desktop.main_window import MainWindow


def test_main_window_has_filezall_title(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "FileZall"


def test_main_window_exposes_connection_and_file_panels(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.connection_bar.host_edit.placeholderText() == "Host"
    assert window.connection_bar.port_edit.text() == "22"
    assert window.connection_bar.auth_mode_selector.itemText(0) == "Password"
    assert window.connection_bar.auth_mode_selector.itemText(1) == "SSH Key"
    assert window.connection_bar.secret_edit.placeholderText() == "Password / passphrase"
    assert window.connection_bar.ssh_key_path_edit.placeholderText() == "SSH key path"
    assert window.local_panel.title.text() == "Local Files"
    assert window.remote_panel.title.text() == "Remote Files"
    assert window.transfer_table.columnCount() == 5
