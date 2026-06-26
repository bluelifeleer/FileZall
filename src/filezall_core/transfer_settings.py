from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TransferSettings:
    max_concurrent: int = 2
    bytes_per_second_limit: int | None = None
