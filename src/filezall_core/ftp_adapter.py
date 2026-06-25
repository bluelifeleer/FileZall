from __future__ import annotations

import ftplib
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from filezall_core.models import Protocol, RemoteFileEntry, SiteProfile
from filezall_core.protocols import RemoteConnectionError


class FtpAdapter:
    def __init__(self, protocol: Protocol, ftp_module=ftplib) -> None:
        if protocol not in {Protocol.FTP, Protocol.FTPS}:
            raise ValueError("FtpAdapter supports only FTP and FTPS")
        self._protocol = protocol
        self._ftp_module = ftp_module
        self._client = None

    def connect(self, site: SiteProfile, password: str | None = None) -> None:
        client = (
            self._ftp_module.FTP_TLS()
            if self._protocol is Protocol.FTPS
            else self._ftp_module.FTP()
        )
        try:
            client.connect(site.host, site.port, timeout=15)
            client.login(user=site.username, passwd=password)
            if self._protocol is Protocol.FTPS:
                client.prot_p()
            self._client = client
        except Exception as exc:
            raise RemoteConnectionError(str(exc)) from exc

    def close(self) -> None:
        if self._client is not None:
            self._client.quit()

    def home_directory(self) -> PurePosixPath:
        return PurePosixPath(self._require_client().pwd())

    def list_directory(self, path: PurePosixPath) -> list[RemoteFileEntry]:
        entries = [
            self._entry_from_mlsd(path, name, facts)
            for name, facts in self._require_client().mlsd(str(path))
        ]
        return sorted(entries, key=lambda entry: (not entry.is_dir, entry.name.lower()))

    def upload_file(self, local_path: Path, remote_path: PurePosixPath) -> None:
        with local_path.open("rb") as file:
            self._require_client().storbinary(f"STOR {remote_path}", file)

    def download_file(self, remote_path: PurePosixPath, local_path: Path) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with local_path.open("wb") as file:
            self._require_client().retrbinary(f"RETR {remote_path}", file.write)

    def remote_size(self, path: PurePosixPath) -> int | None:
        try:
            return int(self._require_client().size(str(path)))
        except Exception:
            return None

    def upload_file_range(
        self,
        local_path: Path,
        remote_path: PurePosixPath,
        offset: int,
    ) -> None:
        with local_path.open("rb") as file:
            file.seek(offset)
            self._require_client().storbinary(f"STOR {remote_path}", file, rest=offset)

    def download_file_range(
        self,
        remote_path: PurePosixPath,
        local_path: Path,
        offset: int,
    ) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with local_path.open("ab") as file:
            self._require_client().retrbinary(f"RETR {remote_path}", file.write, rest=offset)

    def rename(
        self,
        source_path: PurePosixPath,
        destination_path: PurePosixPath,
    ) -> None:
        self._require_client().rename(str(source_path), str(destination_path))

    def _entry_from_mlsd(
        self,
        parent: PurePosixPath,
        name: str,
        facts: dict[str, str],
    ) -> RemoteFileEntry:
        is_dir = facts.get("type") == "dir"
        modified = _parse_mlsd_time(facts.get("modify"))
        return RemoteFileEntry(
            path=parent / name,
            name=name,
            is_dir=is_dir,
            size_bytes=0 if is_dir else int(facts.get("size") or 0),
            modified_time=modified,
        )

    def _require_client(self):
        if self._client is None:
            raise RemoteConnectionError("FTP client is not connected")
        return self._client


def _parse_mlsd_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d%H%M%S").replace(tzinfo=UTC)
    except ValueError:
        return None
