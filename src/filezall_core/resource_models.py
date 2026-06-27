from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CpuStats:
    percent: float


@dataclass(frozen=True)
class MemoryStats:
    total_bytes: int
    used_bytes: int
    available_bytes: int


@dataclass(frozen=True)
class DiskUsage:
    mount: str
    total_bytes: int
    used_bytes: int
    available_bytes: int


@dataclass(frozen=True)
class NetworkStats:
    rx_bytes_per_sec: int
    tx_bytes_per_sec: int


@dataclass(frozen=True)
class ProcessSummary:
    pid: int
    user: str
    name: str
    cpu_percent: float
    memory_percent: float
    command_line: str = ""


@dataclass(frozen=True)
class ProcessDetail:
    pid: int
    user: str
    name: str
    cpu_percent: float
    memory_percent: float
    command_line: str
    start_time: str
    thread_count: int
    status: str


@dataclass(frozen=True)
class ResourceSnapshot:
    cpu: CpuStats
    memory: MemoryStats
    disks: list[DiskUsage]
    network: NetworkStats
    processes: list[ProcessSummary]
