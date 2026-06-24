from __future__ import annotations

from collections.abc import Callable
from pathlib import Path, PurePosixPath

from filezall_core.local_files import list_local_directory
from filezall_core.models import SiteProfile
from filezall_core.session import RemoteSession
from filezall_core.sftp_adapter import SftpAdapter


class MainWindowController:
    def __init__(
        self,
        window,
        local_lister: Callable[[Path], list] = list_local_directory,
        session_factory: Callable[[SiteProfile], RemoteSession] | None = None,
    ) -> None:
        self._window = window
        self._local_lister = local_lister
        self._session_factory = session_factory or (
            lambda site: RemoteSession(site=site, client=SftpAdapter())
        )
        self._session: RemoteSession | None = None

    def load_local_directory(self, path: Path) -> None:
        entries = self._local_lister(path)
        self._window.set_local_entries(entries)
        self._window.show_status(f"Loaded local directory {path}")

    def connect(self, site: SiteProfile, password: str | None = None) -> None:
        self._session = self._session_factory(site)
        entries = self._session.connect_and_list_default(password=password)
        self._window.set_remote_entries(entries, self._session.current_remote_path)
        self._window.show_status(f"Connected to {site.name}")

    def upload_file(self, local_path: Path, remote_path: PurePosixPath) -> None:
        self._require_session().upload_file(local_path, remote_path)
        self._window.show_status(f"Uploaded {local_path.name}")

    def download_file(self, remote_path: PurePosixPath, local_path: Path) -> None:
        self._require_session().download_file(remote_path, local_path)
        self._window.show_status(f"Downloaded {remote_path.name}")

    def _require_session(self) -> RemoteSession:
        if self._session is None:
            raise RuntimeError("Remote session is not connected")
        return self._session
