from __future__ import annotations

from pathlib import Path, PurePosixPath

from filezall_core.models import RemoteFileEntry, SiteProfile
from filezall_core.protocols import RemoteFileClient


class RemoteSession:
    def __init__(self, site: SiteProfile, client: RemoteFileClient) -> None:
        self.site = site
        self.client = client
        self.current_remote_path: PurePosixPath | None = None

    def connect_and_list_default(self, password: str | None = None) -> list[RemoteFileEntry]:
        self.client.connect(self.site, password=password)
        target = self._initial_remote_path()
        self.current_remote_path = target
        return self.client.list_directory(target)

    def list_directory(self, path: PurePosixPath) -> list[RemoteFileEntry]:
        self.current_remote_path = path
        return self.client.list_directory(path)

    def upload_file(self, local_path: Path, remote_path: PurePosixPath) -> None:
        self.client.upload_file(local_path, remote_path)

    def download_file(self, remote_path: PurePosixPath, local_path: Path) -> None:
        self.client.download_file(remote_path, local_path)

    def rename(self, source_path: PurePosixPath, destination_path: PurePosixPath) -> None:
        self.client.rename(source_path, destination_path)

    def delete_path(self, path: PurePosixPath, *, is_dir: bool) -> None:
        self.client.delete_path(path, is_dir=is_dir)

    def make_directory(self, path: PurePosixPath) -> None:
        self.client.make_directory(path)

    def create_file(self, path: PurePosixPath) -> None:
        self.client.create_file(path)

    def close(self) -> None:
        self.client.close()

    def _initial_remote_path(self) -> PurePosixPath:
        if str(self.site.default_remote_path) == "~":
            return self.client.home_directory()
        return self.site.default_remote_path
