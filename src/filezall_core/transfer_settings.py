from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TransferSettings:
    max_concurrent: int = 4
    max_concurrent_per_server: int | None = 2
    bytes_per_second_limit: int | None = None
