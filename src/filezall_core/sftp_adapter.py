from __future__ import annotations

import stat
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import paramiko

from filezall_core.models import AuthMode, RemoteFileEntry, SiteProfile
from filezall_core.protocols import RemoteConnectionError


class SftpAdapter:
    def __init__(self, paramiko_module=paramiko) -> None:
        self._paramiko = paramiko_module
        self._ssh = None
        self._sftp = None

    def connect(self, site: SiteProfile, password: str | None = None) -> None:
        client = self._paramiko.SSHClient()
        client.set_missing_host_key_policy(self._paramiko.AutoAddPolicy())
        kwargs = {
            "hostname": site.host,
            "port": site.port,
            "username": site.username,
            "timeout": 15,
        }

        if site.auth_mode == AuthMode.PASSWORD:
            kwargs["password"] = password
        elif site.auth_mode == AuthMode.SSH_KEY:
            if site.ssh_key_path is None:
                raise RemoteConnectionError("SSH key path is required for SSH key auth")
            kwargs["key_filename"] = str(site.ssh_key_path)
            if password:
                kwargs["passphrase"] = password

        try:
            client.connect(**kwargs)
            self._ssh = client
            self._sftp = client.open_sftp()
        except Exception as exc:
            raise RemoteConnectionError(str(exc)) from exc

    def close(self) -> None:
        if self._sftp:
            self._sftp.close()
        if self._ssh:
            self._ssh.close()

    def home_directory(self) -> PurePosixPath:
        return PurePosixPath(self._require_sftp().normalize("."))

    def list_directory(self, path: PurePosixPath) -> list[RemoteFileEntry]:
        entries: list[RemoteFileEntry] = []
        for attrs in self._require_sftp().listdir_attr(str(path)):
            is_dir = stat.S_ISDIR(attrs.st_mode)
            entries.append(
                RemoteFileEntry(
                    path=path / attrs.filename,
                    name=attrs.filename,
                    is_dir=is_dir,
                    size_bytes=0 if is_dir else int(attrs.st_size),
                    modified_time=datetime.fromtimestamp(attrs.st_mtime, tz=UTC)
                    if attrs.st_mtime
                    else None,
                )
            )
        return sorted(entries, key=lambda entry: (not entry.is_dir, entry.name.lower()))

    def upload_file(self, local_path: Path, remote_path: PurePosixPath) -> None:
        self._require_sftp().put(str(local_path), str(remote_path))

    def download_file(self, remote_path: PurePosixPath, local_path: Path) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self._require_sftp().get(str(remote_path), str(local_path))

    def remote_size(self, path: PurePosixPath) -> int | None:
        try:
            return int(self._require_sftp().stat(str(path)).st_size)
        except FileNotFoundError:
            return None

    def upload_file_range(
        self,
        local_path: Path,
        remote_path: PurePosixPath,
        offset: int,
        progress_callback: Callable[[int], None] | None = None,
    ) -> None:
        bytes_transferred = offset
        with local_path.open("rb") as local_file:
            local_file.seek(offset)
            with self._require_sftp().open(str(remote_path), "ab") as remote_file:
                while chunk := local_file.read(1024 * 1024):
                    remote_file.write(chunk)
                    bytes_transferred += len(chunk)
                    if progress_callback is not None:
                        progress_callback(bytes_transferred)

    def download_file_range(
        self,
        remote_path: PurePosixPath,
        local_path: Path,
        offset: int,
    ) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with self._require_sftp().open(str(remote_path), "rb") as remote_file:
            remote_file.seek(offset)
            with local_path.open("ab") as local_file:
                while chunk := remote_file.read(1024 * 1024):
                    local_file.write(chunk)

    def rename(
        self,
        source_path: PurePosixPath,
        destination_path: PurePosixPath,
    ) -> None:
        self._require_sftp().rename(str(source_path), str(destination_path))

    def delete_path(self, path: PurePosixPath, *, is_dir: bool) -> None:
        sftp = self._require_sftp()
        if is_dir:
            sftp.rmdir(str(path))
            return
        sftp.remove(str(path))

    def make_directory(self, path: PurePosixPath) -> None:
        self._require_sftp().mkdir(str(path))

    def create_file(self, path: PurePosixPath) -> None:
        with self._require_sftp().open(str(path), "w"):
            pass

    def capture(self, command: str) -> str:
        stdout, _stderr = self._exec(command)
        return stdout.read().decode("utf-8", errors="replace")

    def _exec(self, command: str):
        ssh = self._require_ssh()
        _stdin, stdout, stderr = ssh.exec_command(command)
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            error = stderr.read().decode("utf-8", errors="replace").strip()
            raise RemoteConnectionError(
                error or f"Remote command failed with exit status {exit_status}: {command}"
            )
        return stdout, stderr

    def _require_ssh(self):
        if self._ssh is None:
            raise RemoteConnectionError("SSH client is not connected")
        return self._ssh

    def _require_sftp(self):
        if self._sftp is None:
            raise RemoteConnectionError("SFTP client is not connected")
        return self._sftp
