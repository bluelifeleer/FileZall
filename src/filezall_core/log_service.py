from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import re


_SENSITIVE_PATTERNS = [
    re.compile(r"(?i)\b(password|passphrase|token|secret)=([^\s,;]+)"),
    re.compile(r"(?i)\b(FILEZALL_AGENT_TOKEN)=([^\s,;]+)"),
    re.compile(r"(?i)(Authorization:\s*Bearer\s+)([^\s,;]+)"),
]


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
        entry = LogEntry(datetime.now(UTC), redact_sensitive_text(message))
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


def redact_sensitive_text(text: str) -> str:
    redacted = text
    for pattern in _SENSITIVE_PATTERNS:
        redacted = pattern.sub(_redact_match, redacted)
    return redacted


def _redact_match(match: re.Match[str]) -> str:
    if match.group(1).lower().startswith("authorization"):
        return f"{match.group(1)}<redacted>"
    return f"{match.group(1)}=<redacted>"
