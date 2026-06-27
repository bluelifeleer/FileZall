from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class ConnectionRecoverySnapshot:
    state: str
    attempt: int
    next_retry_at: datetime | None
    last_error: str | None


class ConnectionRecoveryState:
    def __init__(self, max_attempts: int = 3, base_delay_seconds: int = 2) -> None:
        self._max_attempts = max_attempts
        self._base_delay_seconds = base_delay_seconds
        self._snapshot = ConnectionRecoverySnapshot(
            state="idle",
            attempt=0,
            next_retry_at=None,
            last_error=None,
        )

    def record_failure(self, error: str, *, now: datetime) -> ConnectionRecoverySnapshot:
        if self._snapshot.state == "blocked":
            return self._snapshot
        attempt = self._snapshot.attempt + 1
        if attempt > self._max_attempts:
            self._snapshot = ConnectionRecoverySnapshot(
                state="blocked",
                attempt=self._max_attempts,
                next_retry_at=None,
                last_error=error,
            )
            return self._snapshot
        delay = self._base_delay_seconds * (2 ** (attempt - 1))
        self._snapshot = ConnectionRecoverySnapshot(
            state="waiting",
            attempt=attempt,
            next_retry_at=now + timedelta(seconds=delay),
            last_error=error,
        )
        return self._snapshot

    def record_success(self) -> ConnectionRecoverySnapshot:
        self._snapshot = ConnectionRecoverySnapshot(
            state="idle",
            attempt=0,
            next_retry_at=None,
            last_error=None,
        )
        return self._snapshot

    def can_retry(self, now: datetime) -> bool:
        if self._snapshot.state != "waiting":
            return False
        return self._snapshot.next_retry_at is not None and self._snapshot.next_retry_at <= now

    def snapshot(self) -> ConnectionRecoverySnapshot:
        return self._snapshot
