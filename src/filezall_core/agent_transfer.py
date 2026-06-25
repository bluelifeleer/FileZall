from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import parse, request


@dataclass(frozen=True)
class ChunkStatus:
    index: int
    size: int
    complete: bool


class AgentTransferClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        opener=None,
        timeout: int = 30,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._opener = opener or request.build_opener()
        self._timeout = timeout

    def upload_chunk(
        self,
        remote_path: str,
        transfer_id: str,
        index: int,
        data: bytes,
    ) -> ChunkStatus:
        query = parse.urlencode({"path": remote_path})
        payload = self._request(
            f"/transfers/{transfer_id}/chunks/{index}?{query}",
            data=data,
        )
        return _chunk_status_from_json(payload)

    def download_chunk(self, remote_path: str, offset: int, size: int) -> bytes:
        query = parse.urlencode({"path": remote_path, "offset": offset, "size": size})
        return self._request_bytes(f"/download-chunk?{query}")

    def chunk_status(self, transfer_id: str) -> list[ChunkStatus]:
        payload = self._request(f"/transfers/{transfer_id}/chunks")
        return [_chunk_status_from_json(row) for row in payload.get("chunks", [])]

    def merge(self, transfer_id: str, remote_path: str, total_size: int) -> bool:
        payload = self._request(
            f"/transfers/{transfer_id}/merge",
            data=json.dumps({"path": remote_path, "total_size": total_size}).encode("utf-8"),
        )
        return bool(payload.get("ok"))

    def verify(self, remote_path: str, checksum: str) -> bool:
        payload = self._request(
            "/files/verify",
            data=json.dumps({"path": remote_path, "checksum": checksum}).encode("utf-8"),
        )
        return bool(payload.get("ok"))

    def _request(self, path: str, data: bytes | None = None) -> dict[str, Any]:
        return json.loads(self._request_bytes(path, data=data).decode("utf-8"))

    def _request_bytes(self, path: str, data: bytes | None = None) -> bytes:
        agent_request = request.Request(f"{self._base_url}{path}", data=data)
        agent_request.add_header("Authorization", f"Bearer {self._token}")
        response = self._opener.open(agent_request, timeout=self._timeout)
        return response.read()


def _chunk_status_from_json(payload: dict[str, Any]) -> ChunkStatus:
    return ChunkStatus(
        index=int(payload["index"]),
        size=int(payload["size"]),
        complete=bool(payload["complete"]),
    )
