from __future__ import annotations

from datetime import datetime


def format_display_time(value: datetime | None) -> str:
    if value is None:
        return ""
    normalized = value
    if normalized.tzinfo is None or normalized.utcoffset() is None:
        normalized = normalized.astimezone()
    return f"{normalized.strftime('%Y-%m-%d %H:%M:%S')} {_timezone_label(normalized)}"


def _timezone_label(value: datetime) -> str:
    offset = value.utcoffset()
    if offset is None:
        return "UTC"
    total_seconds = int(offset.total_seconds())
    sign = "+" if total_seconds >= 0 else "-"
    total_seconds = abs(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60
    return f"UTC{sign}{hours:02d}:{minutes:02d}"
