from __future__ import annotations

import os
from pathlib import Path


class AgentResourceService:
    def __init__(self, proc_root: Path = Path("/proc")) -> None:
        self._proc_root = proc_root

    def resources(self) -> dict:
        processes = self.processes()["processes"]
        return {
            "cpu": {"percent": self._cpu_percent()},
            "memory": self._memory(),
            "disks": [self._disk_usage(Path("/"))],
            "network": {"rx_bytes_per_sec": 0, "tx_bytes_per_sec": 0},
            "processes": processes,
        }

    def processes(self) -> dict:
        if not self._proc_root.exists():
            return {"processes": []}
        rows = []
        for child in self._proc_root.iterdir():
            if child.name.isdigit():
                rows.append(_summary_from_status(child.name, _read_text(child / "status")))
        return {"processes": sorted(rows, key=lambda row: row["pid"])}

    def process_detail(self, pid: int) -> dict:
        process_dir = self._proc_root / str(pid)
        if not process_dir.exists():
            return {
                "pid": pid,
                "user": "",
                "name": "",
                "cpu_percent": 0.0,
                "memory_percent": 0.0,
                "command_line": "",
                "start_time": "",
                "thread_count": 0,
                "status": "unknown",
            }
        status = _read_text(process_dir / "status")
        summary = _summary_from_status(str(pid), status)
        return {
            **summary,
            "command_line": _read_text(process_dir / "cmdline").replace("\x00", " ").strip(),
            "start_time": "",
            "thread_count": _status_int(status, "Threads"),
            "status": _status_text(status, "State") or "unknown",
        }

    def _cpu_percent(self) -> float:
        stat_path = self._proc_root / "stat"
        text = _read_text(stat_path)
        return 0.0 if not text else 0.0

    def _memory(self) -> dict:
        meminfo = _read_text(self._proc_root / "meminfo")
        if not meminfo:
            return {"total_bytes": 0, "used_bytes": 0, "available_bytes": 0}
        return parse_meminfo(meminfo)

    @staticmethod
    def _disk_usage(path: Path) -> dict:
        if not hasattr(os, "statvfs"):
            return {"mount": str(path), "total_bytes": 0, "used_bytes": 0, "available_bytes": 0}
        try:
            usage = os.statvfs(path)
        except OSError:
            return {"mount": str(path), "total_bytes": 0, "used_bytes": 0, "available_bytes": 0}
        total = usage.f_blocks * usage.f_frsize
        available = usage.f_bavail * usage.f_frsize
        return {
            "mount": str(path),
            "total_bytes": total,
            "used_bytes": total - available,
            "available_bytes": available,
        }


def parse_meminfo(text: str) -> dict:
    values = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        parts = raw_value.strip().split()
        if parts:
            values[key] = int(parts[0]) * 1024
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", values.get("MemFree", 0))
    return {
        "total_bytes": total,
        "used_bytes": max(total - available, 0),
        "available_bytes": available,
    }


def parse_proc_stat(previous: str, current: str) -> float:
    previous_values = _cpu_values(previous)
    current_values = _cpu_values(current)
    previous_idle = previous_values[3] + previous_values[4]
    current_idle = current_values[3] + current_values[4]
    previous_total = sum(previous_values)
    current_total = sum(current_values)
    total_delta = current_total - previous_total
    idle_delta = current_idle - previous_idle
    if total_delta <= 0:
        return 0.0
    return round((total_delta - idle_delta) * 100 / total_delta, 1)


def _cpu_values(line: str) -> list[int]:
    return [int(value) for value in line.split()[1:]]


def _summary_from_status(pid: str, status: str) -> dict:
    return {
        "pid": int(pid),
        "user": "",
        "name": _status_text(status, "Name") or "",
        "cpu_percent": 0.0,
        "memory_percent": 0.0,
    }


def _status_text(status: str, key: str) -> str | None:
    prefix = f"{key}:"
    for line in status.splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return None


def _status_int(status: str, key: str) -> int:
    value = _status_text(status, key)
    if not value:
        return 0
    return int(value.split()[0])


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
