from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from filezall_core.redaction import redact_sensitive
from filezall_core.time_format import format_display_time


@dataclass(frozen=True)
class LogRecord:
    timestamp: datetime
    category: str
    level: str
    message: str

    @property
    def created_at(self) -> datetime:
        return self.timestamp

    def format(self) -> str:
        return (
            f"{format_display_time(self.timestamp)} "
            f"[{self.category}] [{self.level}] {self.message}"
        )


LogEntry = LogRecord


class TransferLogService:
    def __init__(self) -> None:
        self._entries: list[LogRecord] = []

    def append(
        self,
        message: str,
        *,
        category: str = "transfer",
        level: str = "info",
    ) -> LogRecord:
        entry = LogRecord(
            timestamp=datetime.now(UTC),
            category=category,
            level=level,
            message=redact_sensitive(message),
        )
        self._entries.append(entry)
        return entry

    def append_connection(self, message: str, *, level: str = "info") -> LogRecord:
        return self.append(message, category="connection", level=level)

    def append_transfer(self, message: str, *, level: str = "info") -> LogRecord:
        return self.append(message, category="transfer", level=level)

    def append_agent(self, message: str, *, level: str = "info") -> LogRecord:
        return self.append(message, category="agent", level=level)

    def append_resource(self, message: str, *, level: str = "info") -> LogRecord:
        return self.append(message, category="resource", level=level)

    def append_error(self, message: str) -> LogRecord:
        return self.append(message, category="error", level="error")

    def records(self) -> list[LogRecord]:
        return list(self._entries)

    def entries(self) -> list[LogRecord]:
        return list(self._entries)

    def export(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(entry.format() for entry in self._entries) + ("\n" if self._entries else ""),
            encoding="utf-8",
        )


def redact_sensitive_text(text: str) -> str:
    return redact_sensitive(text)
