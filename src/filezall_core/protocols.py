from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Protocol as TypingProtocol

from filezall_core.models import RemoteFileEntry, SiteProfile


class RemoteConnectionError(RuntimeError):
    pass


class RemoteFileClient(TypingProtocol):
    """M2-minimal remote file interface.

    Later protocol milestones add stat, mkdir, delete, rename, move, and resume
    capability without changing the desktop workflow boundary.
    """

    def connect(self, site: SiteProfile, password: str | None = None) -> None:
        ...

    def close(self) -> None:
        ...

    def home_directory(self) -> PurePosixPath:
        ...

    def list_directory(self, path: PurePosixPath) -> list[RemoteFileEntry]:
        ...

    def upload_file(self, local_path: Path, remote_path: PurePosixPath) -> None:
        ...

    def download_file(self, remote_path: PurePosixPath, local_path: Path) -> None:
        ...


class FakeRemoteClient:
    def __init__(
        self,
        entries: dict[PurePosixPath, list[RemoteFileEntry]],
        home: PurePosixPath,
    ) -> None:
        self._entries = entries
        self._home = home
        self.connected_site: SiteProfile | None = None
        self.password: str | None = None
        self.uploads: list[tuple[Path, PurePosixPath]] = []
        self.downloads: list[tuple[PurePosixPath, Path]] = []
        self.closed = False

    def connect(self, site: SiteProfile, password: str | None = None) -> None:
        self.connected_site = site
        self.password = password

    def close(self) -> None:
        self.closed = True

    def home_directory(self) -> PurePosixPath:
        return self._home

    def list_directory(self, path: PurePosixPath) -> list[RemoteFileEntry]:
        return self._entries.get(path, [])

    def upload_file(self, local_path: Path, remote_path: PurePosixPath) -> None:
        self.uploads.append((local_path, remote_path))

    def download_file(self, remote_path: PurePosixPath, local_path: Path) -> None:
        self.downloads.append((remote_path, local_path))
