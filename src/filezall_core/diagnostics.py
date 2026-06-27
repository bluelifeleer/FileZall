from __future__ import annotations

import json
import platform
import sys
import zipfile
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from filezall_core import __version__
from filezall_core.log_service import TransferLogService
from filezall_core.redaction import redact_sensitive


class DiagnosticPackageBuilder:
    def __init__(
        self,
        *,
        log_service: TransferLogService,
        logs_dir: Path | None = None,
        state_provider: Callable[[], Mapping] | None = None,
    ) -> None:
        self._log_service = log_service
        self._logs_dir = logs_dir
        self._state_provider = state_provider

    def build(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(self._manifest(), indent=2))
            archive.writestr("logs/session.log", self._session_log_text())
            archive.writestr("logs/session-records.json", self._session_records_json())
            if self._state_provider is not None:
                archive.writestr("state/snapshot.json", self._state_snapshot_json())
            for log_path in self._runtime_log_paths():
                archive.writestr(f"logs/{log_path.name}", self._runtime_log_text(log_path))
        return path

    def _manifest(self) -> dict[str, str]:
        return {
            "app": "FileZall",
            "version": __version__,
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        }

    def _session_log_text(self) -> str:
        entries = self._log_service.entries()
        return "\n".join(entry.format() for entry in entries) + ("\n" if entries else "")

    def _session_records_json(self) -> str:
        records = [
            {
                "timestamp": record.timestamp.isoformat(timespec="seconds"),
                "category": record.category,
                "level": record.level,
                "message": record.message,
            }
            for record in self._log_service.records()
        ]
        return json.dumps(records, indent=2)

    def _runtime_log_paths(self) -> list[Path]:
        if self._logs_dir is None or not self._logs_dir.exists():
            return []
        return [
            path
            for path in sorted(self._logs_dir.glob("*.log"))
            if path.is_file()
        ]

    def _runtime_log_text(self, path: Path) -> str:
        return redact_sensitive(path.read_text(encoding="utf-8", errors="replace"))

    def _state_snapshot_json(self) -> str:
        state = self._state_provider() if self._state_provider is not None else {}
        return json.dumps(_redact_state(state), indent=2)


def _redact_state(value):
    if isinstance(value, Mapping):
        return {
            str(key): (
                "<redacted>"
                if _is_sensitive_key(str(key))
                else _redact_state(nested_value)
            )
            for key, nested_value in value.items()
        }
    if isinstance(value, list | tuple):
        return [_redact_state(item) for item in value]
    if isinstance(value, str):
        return redact_sensitive(value)
    return value


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in ("password", "passphrase", "token", "secret"))
