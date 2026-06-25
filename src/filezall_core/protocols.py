from __future__ import annotations

from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Protocol as TypingProtocol

from filezall_core.models import RemoteFileEntry, SiteProfile


class RemoteConnectionError(RuntimeError):
    pass


class RemoteFileClient(TypingProtocol):
    """Remote file interface used by sessions and resumable transfer runners."""

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

    def remote_size(self, path: PurePosixPath) -> int | None:
        ...

    def upload_file_range(
        self,
        local_path: Path,
        remote_path: PurePosixPath,
        offset: int,
        progress_callback: Callable[[int], None] | None = None,
    ) -> None:
        ...

    def download_file_range(
        self,
        remote_path: PurePosixPath,
        local_path: Path,
        offset: int,
    ) -> None:
        ...

    def rename(
        self,
        source_path: PurePosixPath,
        destination_path: PurePosixPath,
    ) -> None:
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
        self.remote_sizes: dict[PurePosixPath, int] = {}
        self.range_uploads: list[tuple[Path, PurePosixPath, int]] = []
        self.range_downloads: list[tuple[PurePosixPath, Path, int]] = []
        self.renames: list[tuple[PurePosixPath, PurePosixPath]] = []
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

    def remote_size(self, path: PurePosixPath) -> int | None:
        return self.remote_sizes.get(path)

    def upload_file_range(
        self,
        local_path: Path,
        remote_path: PurePosixPath,
        offset: int,
        progress_callback: Callable[[int], None] | None = None,
    ) -> None:
        self.range_uploads.append((local_path, remote_path, offset))
        if progress_callback is not None:
            progress_callback(local_path.stat().st_size)

    def download_file_range(
        self,
        remote_path: PurePosixPath,
        local_path: Path,
        offset: int,
    ) -> None:
        self.range_downloads.append((remote_path, local_path, offset))

    def rename(
        self,
        source_path: PurePosixPath,
        destination_path: PurePosixPath,
    ) -> None:
        self.renames.append((source_path, destination_path))
