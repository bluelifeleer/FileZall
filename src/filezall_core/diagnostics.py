from __future__ import annotations

import json
import platform
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from filezall_core import __version__
from filezall_core.log_service import TransferLogService


class DiagnosticPackageBuilder:
    def __init__(self, *, log_service: TransferLogService, logs_dir: Path | None = None) -> None:
        self._log_service = log_service
        self._logs_dir = logs_dir

    def build(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("manifest.json", json.dumps(self._manifest(), indent=2))
            archive.writestr("logs/session.log", self._session_log_text())
            for log_path in self._runtime_log_paths():
                archive.write(log_path, f"logs/{log_path.name}")
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

    def _runtime_log_paths(self) -> list[Path]:
        if self._logs_dir is None or not self._logs_dir.exists():
            return []
        return [
            path
            for path in sorted(self._logs_dir.glob("*.log"))
            if path.is_file()
        ]
