from filezall_desktop.main_window import MainWindow


def test_main_window_has_filezall_title(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "FileZall"
