from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path

try:
    import pwd
except ImportError:  # pragma: no cover - Windows test environment.
    pwd = None


class AgentResourceService:
    def __init__(
        self,
        proc_root: Path = Path("/proc"),
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._proc_root = proc_root
        self._clock = clock
        self._previous_cpu_stat: str | None = self._read_cpu_stat()
        self._previous_network_sample: tuple[dict[str, int], float] | None = (
            self._read_network_sample()
        )

    def resources(self) -> dict:
        processes = self.processes()["processes"]
        return {
            "cpu": {"percent": self._cpu_percent()},
            "memory": self._memory(),
            "disks": [self._disk_usage(Path("/"))],
            "network": self._network(),
            "processes": processes,
        }

    def processes(self) -> dict:
        if not self._proc_root.exists():
            return {"processes": []}
        memory_total = self._memory().get("total_bytes", 0)
        rows = []
        for child in self._proc_root.iterdir():
            if child.name.isdigit():
                rows.append(
                    _summary_from_process_dir(
                        child.name,
                        child,
                        memory_total_bytes=memory_total,
                    )
                )
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
        summary = _summary_from_process_dir(
            str(pid),
            process_dir,
            memory_total_bytes=self._memory().get("total_bytes", 0),
            status=status,
        )
        return {
            **summary,
            "start_time": "",
            "thread_count": _status_int(status, "Threads"),
            "status": _status_text(status, "State") or "unknown",
        }

    def _cpu_percent(self) -> float:
        current = self._read_cpu_stat()
        if current is None:
            return 0.0
        previous = self._previous_cpu_stat
        self._previous_cpu_stat = current
        if previous is None:
            return 0.0
        return parse_proc_stat(previous, current)

    def _read_cpu_stat(self) -> str | None:
        text = _read_text(self._proc_root / "stat")
        if not text:
            return None
        return text.splitlines()[0]

    def _memory(self) -> dict:
        meminfo = _read_text(self._proc_root / "meminfo")
        if not meminfo:
            return {"total_bytes": 0, "used_bytes": 0, "available_bytes": 0}
        return parse_meminfo(meminfo)

    def _network(self) -> dict:
        current_sample = self._read_network_sample()
        if current_sample is None:
            return {"rx_bytes_per_sec": 0, "tx_bytes_per_sec": 0}
        previous_sample = self._previous_network_sample
        self._previous_network_sample = current_sample
        if previous_sample is None:
            return {"rx_bytes_per_sec": 0, "tx_bytes_per_sec": 0}
        previous, previous_time = previous_sample
        current, current_time = current_sample
        elapsed = current_time - previous_time
        if elapsed <= 0:
            return {"rx_bytes_per_sec": 0, "tx_bytes_per_sec": 0}
        rx_delta = max(current["rx_bytes"] - previous["rx_bytes"], 0)
        tx_delta = max(current["tx_bytes"] - previous["tx_bytes"], 0)
        return {
            "rx_bytes_per_sec": int(round(rx_delta / elapsed)),
            "tx_bytes_per_sec": int(round(tx_delta / elapsed)),
        }

    def _read_network_sample(self) -> tuple[dict[str, int], float] | None:
        net_dev = _read_text(self._proc_root / "net" / "dev")
        if not net_dev:
            return None
        return parse_net_dev(net_dev), self._clock()

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


def parse_net_dev(text: str) -> dict:
    rx_bytes = 0
    tx_bytes = 0
    for line in text.splitlines():
        if ":" not in line:
            continue
        interface, raw_values = line.split(":", 1)
        if interface.strip() == "lo":
            continue
        values = raw_values.split()
        if len(values) < 16:
            continue
        rx_bytes += int(values[0])
        tx_bytes += int(values[8])
    return {"rx_bytes": rx_bytes, "tx_bytes": tx_bytes}


def _cpu_values(line: str) -> list[int]:
    return [int(value) for value in line.split()[1:]]


def _summary_from_process_dir(
    pid: str,
    process_dir: Path,
    *,
    memory_total_bytes: int,
    status: str | None = None,
) -> dict:
    status = status if status is not None else _read_text(process_dir / "status")
    rss_bytes = _status_int(status, "VmRSS") * 1024
    memory_percent = 0.0
    if memory_total_bytes > 0:
        memory_percent = round(rss_bytes * 100 / memory_total_bytes, 1)
    return {
        "pid": int(pid),
        "user": _status_user(status),
        "name": _status_text(status, "Name") or "",
        "cpu_percent": 0.0,
        "memory_percent": memory_percent,
        "command_line": _command_line(process_dir / "cmdline"),
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


def _status_user(status: str) -> str:
    value = _status_text(status, "Uid")
    if not value:
        return ""
    uid_text = value.split()[0]
    if pwd is None:
        return uid_text
    try:
        return pwd.getpwuid(int(uid_text)).pw_name
    except (KeyError, ValueError):
        return uid_text


def _command_line(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    return " ".join(part.decode("utf-8", errors="replace") for part in raw.split(b"\x00") if part)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
