from __future__ import annotations

from pathlib import Path, PurePosixPath

from filezall_core.models import TransferItem


def part_path_for(path: Path | PurePosixPath) -> Path | PurePosixPath:
    return path.with_name(f".filezall.{path.name}.part")


def local_resume_offset(item: TransferItem) -> int:
    if isinstance(item.temporary_path, Path) and item.temporary_path.exists():
        return min(item.temporary_path.stat().st_size, item.size_bytes)
    return 0
