from filezall_desktop.main_window import MainWindow
from PySide6.QtCore import Qt

from filezall_core.models import AuthMode, Protocol, SiteProfile


class FakeController:
    def __init__(self) -> None:
        self.loaded_sites = False
        self.connect_calls = []
        self.local_refreshes = []
        self.remote_refreshes = []
        self.uploads = []
        self.downloads = []

    def load_saved_sites(self) -> None:
        self.loaded_sites = True

    def connect(self, site, password=None) -> None:
        self.connect_calls.append((site, password))

    def load_local_directory(self, path) -> None:
        self.local_refreshes.append(path)

    def list_remote_directory(self, path) -> None:
        self.remote_refreshes.append(path)

    def upload_file(self, local_path, remote_path) -> None:
        self.uploads.append((local_path, remote_path))

    def download_file(self, remote_path, local_path) -> None:
        self.downloads.append((remote_path, local_path))


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
    assert window.local_panel.action_button.text() == "Upload"
    assert window.remote_panel.action_button.text() == "Download"
    assert window.transfer_table.columnCount() == 5


def test_main_window_loads_sites_and_connects_button_to_controller(qtbot) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    window.connection_bar.host_edit.setText("example.com")
    window.connection_bar.username_edit.setText("deploy")
    window.connection_bar.secret_edit.setText("secret")
    window.remote_panel.path_edit.setText("/var/www")

    qtbot.mouseClick(window.connection_bar.connect_button, Qt.MouseButton.LeftButton)

    site, password = controller.connect_calls[0]
    assert controller.loaded_sites is True
    assert site.host == "example.com"
    assert site.username == "deploy"
    assert str(site.default_remote_path) == "/var/www"
    assert password == "secret"


def test_main_window_connects_selected_saved_site_with_stored_credential_ref(qtbot) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    saved_site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
        credential_ref="site-1:password",
    )
    window.set_site_profiles([saved_site])
    window.connection_bar.site_selector.setCurrentIndex(1)

    qtbot.mouseClick(window.connection_bar.connect_button, Qt.MouseButton.LeftButton)

    site, password = controller.connect_calls[0]
    assert site == saved_site
    assert password is None


def test_main_window_refresh_upload_and_download_buttons_call_controller(qtbot, tmp_path) -> None:
    controller = FakeController()
    window = MainWindow(controller=controller)
    qtbot.addWidget(window)
    local_root = tmp_path / "local"
    local_root.mkdir()
    (local_root / "app.txt").write_text("hello", encoding="utf-8")
    window.local_panel.path_edit.setText(str(local_root))
    window.remote_panel.path_edit.setText("/home/deploy")
    window.local_panel.set_placeholder_row("app.txt")
    window.remote_panel.set_placeholder_row("remote.txt")
    window.local_panel.table.selectRow(0)
    window.remote_panel.table.selectRow(0)

    qtbot.mouseClick(window.local_panel.refresh_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window.remote_panel.refresh_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window.local_panel.action_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window.remote_panel.action_button, Qt.MouseButton.LeftButton)

    assert controller.local_refreshes == [local_root]
    assert str(controller.remote_refreshes[0]) == "/home/deploy"
    assert controller.uploads == [(local_root / "app.txt", controller.remote_refreshes[0] / "app.txt")]
    assert controller.downloads == [(controller.remote_refreshes[0] / "remote.txt", local_root / "remote.txt")]
