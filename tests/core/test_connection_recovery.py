from datetime import UTC, datetime, timedelta

from filezall_core.connection_recovery import ConnectionRecoveryState


def test_connection_recovery_schedules_bounded_backoff_and_blocks_after_limit() -> None:
    now = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
    recovery = ConnectionRecoveryState(max_attempts=3, base_delay_seconds=2)

    first = recovery.record_failure("heartbeat lost", now=now)
    second = recovery.record_failure("heartbeat lost", now=now + timedelta(seconds=2))
    third = recovery.record_failure("heartbeat lost", now=now + timedelta(seconds=6))
    blocked = recovery.record_failure("heartbeat lost", now=now + timedelta(seconds=14))

    assert first.state == "waiting"
    assert first.attempt == 1
    assert first.next_retry_at == now + timedelta(seconds=2)
    assert second.next_retry_at == now + timedelta(seconds=6)
    assert third.next_retry_at == now + timedelta(seconds=14)
    assert blocked.state == "blocked"
    assert blocked.attempt == 3
    assert blocked.next_retry_at is None
    assert blocked.last_error == "heartbeat lost"


def test_connection_recovery_reports_readiness_and_resets_after_success() -> None:
    now = datetime(2026, 6, 27, 12, 0, tzinfo=UTC)
    recovery = ConnectionRecoveryState(max_attempts=3, base_delay_seconds=2)

    recovery.record_failure("timeout", now=now)

    assert recovery.can_retry(now + timedelta(seconds=1)) is False
    assert recovery.can_retry(now + timedelta(seconds=2)) is True

    recovered = recovery.record_success()

    assert recovered.state == "idle"
    assert recovered.attempt == 0
    assert recovered.next_retry_at is None
    assert recovered.last_error is None
