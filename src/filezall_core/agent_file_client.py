from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path, PurePosixPath
from urllib import parse, request

from filezall_core.agent_transfer import AgentTransferClient
from filezall_core.models import RemoteFileEntry, SiteProfile


class AgentHttpFileClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        opener=None,
        chunk_size: int = 1024 * 1024,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._opener = opener or request.build_opener()
        self._chunk_size = chunk_size
        self._transfer = AgentTransferClient(
            self._base_url,
            token=token,
            opener=self._opener,
        )
        self.connected_site: SiteProfile | None = None

    def connect(self, site: SiteProfile, password: str | None = None) -> None:
        self.connected_site = site

    def close(self) -> None:
        pass

    def home_directory(self) -> PurePosixPath:
        return PurePosixPath("/")

    def list_directory(self, path: PurePosixPath) -> list[RemoteFileEntry]:
        query = parse.urlencode({"path": str(path)})
        payload = self._get_json(f"/files/list?{query}")
        return [
            RemoteFileEntry(
                path=PurePosixPath(str(row["path"])),
                name=str(row["name"]),
                is_dir=bool(row["is_dir"]),
                size_bytes=int(row["size_bytes"]),
                modified_time=datetime.fromisoformat(str(row["modified_time"]))
                if row.get("modified_time")
                else None,
            )
            for row in payload.get("entries", [])
        ]

    def upload_file(self, local_path: Path, remote_path: PurePosixPath) -> None:
        self.upload_file_range(local_path, remote_path, offset=0)

    def download_file(self, remote_path: PurePosixPath, local_path: Path) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        local_path.write_bytes(b"")
        self.download_file_range(remote_path, local_path, offset=0)

    def remote_size(self, path: PurePosixPath) -> int | None:
        query = parse.urlencode({"path": str(path)})
        payload = self._get_json(f"/files/size?{query}")
        if not payload.get("exists", False):
            return None
        return int(payload["size"])

    def upload_file_range(
        self,
        local_path: Path,
        remote_path: PurePosixPath,
        offset: int,
    ) -> None:
        transfer_id = _transfer_id(remote_path)
        total_size = local_path.stat().st_size
        with local_path.open("rb") as file:
            file.seek(offset)
            chunk_index = offset // self._chunk_size
            while data := file.read(self._chunk_size):
                self._transfer.upload_chunk(str(remote_path), transfer_id, chunk_index, data)
                chunk_index += 1
        self._transfer.merge(transfer_id, str(remote_path), total_size)

    def download_file_range(
        self,
        remote_path: PurePosixPath,
        local_path: Path,
        offset: int,
    ) -> None:
        remote_size = self.remote_size(remote_path)
        if remote_size is None:
            remote_size = offset + self._chunk_size
        current = offset
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with local_path.open("ab") as file:
            while current < remote_size:
                size = min(self._chunk_size, remote_size - current)
                data = self._transfer.download_chunk(str(remote_path), current, size)
                if not data:
                    break
                file.write(data)
                current += len(data)

    def rename(
        self,
        source_path: PurePosixPath,
        destination_path: PurePosixPath,
    ) -> None:
        self._post_json(
            "/files/rename",
            {"source": str(source_path), "destination": str(destination_path)},
        )

    def _get_json(self, path: str) -> dict:
        agent_request = request.Request(f"{self._base_url}{path}")
        agent_request.add_header("Authorization", f"Bearer {self._token}")
        response = self._opener.open(agent_request, timeout=30)
        return json.loads(response.read().decode("utf-8"))

    def _post_json(self, path: str, payload: dict) -> dict:
        agent_request = request.Request(
            f"{self._base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
        )
        agent_request.add_header("Authorization", f"Bearer {self._token}")
        response = self._opener.open(agent_request, timeout=30)
        return json.loads(response.read().decode("utf-8"))


def _transfer_id(remote_path: PurePosixPath) -> str:
    return parse.quote(str(remote_path), safe="")
