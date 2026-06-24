from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path, PurePosixPath


class Protocol(StrEnum):
    SFTP = "sftp"
    FTP = "ftp"
    FTPS = "ftps"
    AGENT_HTTP = "agent_http"


class AuthMode(StrEnum):
    PASSWORD = "password"
    SSH_KEY = "ssh_key"


class Direction(StrEnum):
    UPLOAD = "upload"
    DOWNLOAD = "download"


class ConflictPolicy(StrEnum):
    OVERWRITE = "overwrite"
    SKIP = "skip"
    RENAME = "rename"


class TransferStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELED = "canceled"


@dataclass(frozen=True)
class SiteProfile:
    id: str
    name: str
    host: str
    port: int
    protocol: Protocol
    username: str
    auth_mode: AuthMode
    default_remote_path: PurePosixPath = PurePosixPath("~")
    default_local_path: Path | None = None
    credential_ref: str | None = None
    ssh_key_path: Path | None = None
    agent_enabled: bool = False
    agent_token_ref: str | None = None


@dataclass(frozen=True)
class TransferItem:
    id: str
    task_id: str
    server_id: str
    direction: Direction
    source_path: Path | PurePosixPath
    destination_path: Path | PurePosixPath
    temporary_path: Path | PurePosixPath
    size_bytes: int
    protocol: Protocol
    bytes_transferred: int = 0
    status: TransferStatus = TransferStatus.PENDING
    retry_count: int = 0
    last_error: str | None = None

    def with_progress(self, bytes_transferred: int) -> TransferItem:
        next_status = (
            TransferStatus.COMPLETED
            if bytes_transferred >= self.size_bytes
            else TransferStatus.RUNNING
        )
        return replace(
            self,
            bytes_transferred=min(bytes_transferred, self.size_bytes),
            status=next_status,
        )


@dataclass(frozen=True)
class TransferTask:
    id: str
    server_id: str
    direction: Direction
    source_path: Path | PurePosixPath
    destination_path: Path | PurePosixPath
    protocol: Protocol
    conflict_policy: ConflictPolicy
    status: TransferStatus = TransferStatus.PENDING

    def create_item(
        self,
        item_id: str,
        relative_path: PurePosixPath,
        size_bytes: int,
    ) -> TransferItem:
        destination = self._join_path(self.destination_path, relative_path)
        return TransferItem(
            id=item_id,
            task_id=self.id,
            server_id=self.server_id,
            direction=self.direction,
            source_path=self._join_path(self.source_path, relative_path),
            destination_path=destination,
            temporary_path=self._temporary_path(destination),
            size_bytes=size_bytes,
            protocol=self.protocol,
        )

    @staticmethod
    def _join_path(base: Path | PurePosixPath, relative: PurePosixPath) -> Path | PurePosixPath:
        if isinstance(base, Path):
            return base.joinpath(*relative.parts)
        return base.joinpath(relative)

    @staticmethod
    def _temporary_path(path: Path | PurePosixPath) -> Path | PurePosixPath:
        return path.with_name(f".filezall.{path.name}.part")
