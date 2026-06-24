from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from filezall_core.models import LocalFileEntry


def list_local_directory(path: Path) -> list[LocalFileEntry]:
    if not path.is_dir():
        raise NotADirectoryError(str(path))

    entries: list[LocalFileEntry] = []
    for child in path.iterdir():
        stat = child.stat()
        entries.append(
            LocalFileEntry(
                path=child,
                name=child.name,
                is_dir=child.is_dir(),
                size_bytes=0 if child.is_dir() else stat.st_size,
                modified_time=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
            )
        )

    return sorted(entries, key=lambda entry: (not entry.is_dir, entry.name.lower()))
