from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass(frozen=True)
class LogEntry:
    created_at: datetime
    message: str

    def format(self) -> str:
        return f"{self.created_at.isoformat(timespec='seconds')} {self.message}"


class TransferLogService:
    def __init__(self) -> None:
        self._entries: list[LogEntry] = []

    def append(self, message: str) -> LogEntry:
        entry = LogEntry(datetime.now(UTC), message)
        self._entries.append(entry)
        return entry

    def entries(self) -> list[LogEntry]:
        return list(self._entries)

    def export(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(entry.format() for entry in self._entries) + ("\n" if self._entries else ""),
            encoding="utf-8",
        )
