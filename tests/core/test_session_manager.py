from pathlib import PurePosixPath

from filezall_core.models import AuthMode, Protocol, RemoteFileEntry, SiteProfile
from filezall_core.session_manager import SessionManager


class FakeSession:
    def __init__(self, site: SiteProfile) -> None:
        self.site = site
        self.password = None
        self.closed = False

    def connect_and_list_default(self, password=None):
        self.password = password
        return [
            RemoteFileEntry(
                path=PurePosixPath("/home/deploy/app.log"),
                name="app.log",
                is_dir=False,
                size_bytes=10,
                modified_time=None,
            )
        ]

    def close(self) -> None:
        self.closed = True


def test_session_manager_tracks_multiple_connected_sites() -> None:
    sessions = {}
    manager = SessionManager(
        session_factory=lambda site: sessions.setdefault(site.id, FakeSession(site))
    )
    site_1 = _site("site-1")
    site_2 = _site("site-2")

    entries = manager.connect(site_1, password="one")
    manager.connect(site_2, password="two")

    assert entries[0].name == "app.log"
    assert manager.list_site_ids() == ["site-1", "site-2"]
    assert manager.active() is sessions["site-2"]
    assert sessions["site-1"].password == "one"
    assert sessions["site-2"].password == "two"

    manager.switch("site-1")
    assert manager.active() is sessions["site-1"]


def test_session_manager_disconnects_one_or_all_sites() -> None:
    sessions = {}
    manager = SessionManager(
        session_factory=lambda site: sessions.setdefault(site.id, FakeSession(site))
    )
    manager.connect(_site("site-1"))
    manager.connect(_site("site-2"))

    manager.disconnect("site-1")

    assert sessions["site-1"].closed is True
    assert sessions["site-2"].closed is False
    assert manager.list_site_ids() == ["site-2"]

    manager.disconnect_all()

    assert sessions["site-2"].closed is True
    assert manager.list_site_ids() == []


def _site(site_id: str) -> SiteProfile:
    return SiteProfile(
        id=site_id,
        name=site_id,
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )
