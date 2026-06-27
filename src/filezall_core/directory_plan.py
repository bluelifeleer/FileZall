from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from filezall_core.models import Direction
from filezall_core.protocols import RemoteFileClient


@dataclass(frozen=True)
class DirectoryTransferItemPlan:
    source_path: Path | PurePosixPath
    destination_path: Path | PurePosixPath
    relative_path: PurePosixPath
    size_bytes: int
    direction: Direction


@dataclass(frozen=True)
class DirectoryTransferPlan:
    root: Path | PurePosixPath
    destination_root: Path | PurePosixPath
    items: list[DirectoryTransferItemPlan]

    @property
    def total_files(self) -> int:
        return len(self.items)

    @property
    def total_bytes(self) -> int:
        return sum(item.size_bytes for item in self.items)


def plan_local_directory(
    root: Path,
    destination_root: Path | PurePosixPath,
    *,
    direction: Direction,
) -> DirectoryTransferPlan:
    items = []
    for path in sorted((candidate for candidate in root.rglob("*") if candidate.is_file()), key=str):
        relative_path = PurePosixPath(path.relative_to(root).as_posix())
        items.append(
            DirectoryTransferItemPlan(
                source_path=path,
                destination_path=_join(destination_root, relative_path),
                relative_path=relative_path,
                size_bytes=path.stat().st_size,
                direction=direction,
            )
        )
    return DirectoryTransferPlan(root=root, destination_root=destination_root, items=items)


def plan_remote_directory(
    client: RemoteFileClient,
    root: PurePosixPath,
    destination_root: Path | PurePosixPath,
    *,
    direction: Direction,
) -> DirectoryTransferPlan:
    items = []
    for entry in sorted(client.walk_directory(root), key=lambda item: str(item.path)):
        relative_path = PurePosixPath(entry.path.relative_to(root).as_posix())
        items.append(
            DirectoryTransferItemPlan(
                source_path=entry.path,
                destination_path=_join(destination_root, relative_path),
                relative_path=relative_path,
                size_bytes=entry.size_bytes,
                direction=direction,
            )
        )
    return DirectoryTransferPlan(root=root, destination_root=destination_root, items=items)


def _join(base: Path | PurePosixPath, relative_path: PurePosixPath) -> Path | PurePosixPath:
    if isinstance(base, Path):
        return base.joinpath(*relative_path.parts)
    return base.joinpath(relative_path)
