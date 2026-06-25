from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AgentConfig:
    token: str
    root: Path | None = None
    host: str = "127.0.0.1"
    port: int = 8765

    def resolve_path(self, path: str) -> Path:
        if self.root is None:
            return Path(path).expanduser()

        root = self.root.resolve()
        relative = Path(path.lstrip("/"))
        candidate = (root / relative).resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("Path is outside agent root")
        return candidate
