from __future__ import annotations

import hashlib
from pathlib import Path

from filezall_agent.config import AgentConfig


class AgentFileService:
    def __init__(self, config: AgentConfig) -> None:
        self._config = config

    def list_directory(self, path: str) -> list[dict]:
        directory = self._config.resolve_path(path)
        entries = []
        for child in sorted(directory.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
            entries.append(_entry_payload(self._config, child))
        return entries

    def walk_directory(self, path: str) -> list[dict]:
        directory = self._config.resolve_path(path)
        entries = []
        for child in sorted(directory.rglob("*"), key=lambda item: item.relative_to(directory).as_posix().lower()):
            if child.is_file():
                entries.append(_entry_payload(self._config, child))
        return entries

    def file_size(self, path: str) -> dict:
        target = self._config.resolve_path(path)
        if not target.exists():
            return {"exists": False, "size": 0}
        return {"exists": True, "size": target.stat().st_size}

    def rename(self, source: str, destination: str) -> dict:
        source_path = self._config.resolve_path(source)
        destination_path = self._config.resolve_path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.replace(destination_path)
        return {"ok": True}

    def delete_path(self, path: str, is_dir: bool) -> dict:
        target = self._config.resolve_path(path)
        if is_dir or target.is_dir():
            target.rmdir()
        else:
            target.unlink()
        return {"ok": True}

    def make_directory(self, path: str) -> dict:
        self._config.resolve_path(path).mkdir(parents=True, exist_ok=True)
        return {"ok": True}

    def create_file(self, path: str) -> dict:
        target = self._config.resolve_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch(exist_ok=True)
        return {"ok": True}

    def verify(self, path: str, checksum: str) -> dict:
        algorithm, _, expected = checksum.partition(":")
        if algorithm != "sha256" or not expected:
            return {"ok": False}
        actual = hashlib.sha256(self._config.resolve_path(path).read_bytes()).hexdigest()
        return {"ok": actual == expected}

    def write_chunk(self, remote_path: str, transfer_id: str, index: int, data: bytes) -> dict:
        chunk_path = self._chunk_path(transfer_id, index)
        chunk_path.parent.mkdir(parents=True, exist_ok=True)
        chunk_path.write_bytes(data)
        metadata = self._transfer_dir(transfer_id) / "remote_path.txt"
        metadata.write_text(remote_path, encoding="utf-8")
        return {"index": index, "size": len(data), "complete": True}

    def chunk_status(self, transfer_id: str) -> dict:
        transfer_dir = self._transfer_dir(transfer_id)
        chunks = []
        if transfer_dir.exists():
            for chunk in sorted(transfer_dir.glob("*.chunk"), key=lambda item: int(item.stem)):
                chunks.append({"index": int(chunk.stem), "size": chunk.stat().st_size, "complete": True})
        return {"chunks": chunks}

    def merge(self, transfer_id: str, remote_path: str, total_size: int) -> dict:
        destination = self._config.resolve_path(remote_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        with destination.open("wb") as output:
            for status in self.chunk_status(transfer_id)["chunks"]:
                data = self._chunk_path(transfer_id, status["index"]).read_bytes()
                output.write(data)
                written += len(data)
        return {"ok": written == total_size}

    def download_chunk(self, remote_path: str, offset: int, size: int) -> bytes:
        with self._config.resolve_path(remote_path).open("rb") as file:
            file.seek(offset)
            return file.read(size)

    def _transfer_dir(self, transfer_id: str) -> Path:
        root = self._config.root or Path("/")
        return root / ".filezall-agent" / "transfers" / transfer_id

    def _chunk_path(self, transfer_id: str, index: int) -> Path:
        return self._transfer_dir(transfer_id) / f"{index}.chunk"


def _display_path(config: AgentConfig, path: Path) -> str:
    if config.root is None:
        return path.as_posix()
    return "/" + path.resolve().relative_to(config.root.resolve()).as_posix()


def _entry_payload(config: AgentConfig, path: Path) -> dict:
    stat = path.stat()
    return {
        "path": _display_path(config, path),
        "name": path.name,
        "is_dir": path.is_dir(),
        "size_bytes": 0 if path.is_dir() else stat.st_size,
        "modified_time": _modified_time(stat.st_mtime),
    }


def _modified_time(timestamp: float) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()
