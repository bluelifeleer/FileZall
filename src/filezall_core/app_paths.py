from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    root: Path
    database: Path
    logs: Path
    downloads: Path

    def ensure_directories(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.logs.mkdir(parents=True, exist_ok=True)
        self.downloads.mkdir(parents=True, exist_ok=True)


def resolve_app_paths() -> AppPaths:
    override = os.environ.get("FILEZALL_HOME")
    root = Path(override).expanduser() if override else _default_root()
    return AppPaths(
        root=root,
        database=root / "filezall.sqlite3",
        logs=root / "logs",
        downloads=root / "downloads",
    )


def _default_root() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "FileZall"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "FileZall"
    return Path.home() / ".local" / "share" / "filezall"
