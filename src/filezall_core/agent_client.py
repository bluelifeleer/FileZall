from __future__ import annotations

import json
from typing import Any
from urllib import request

from filezall_core.resource_models import (
    CpuStats,
    DiskUsage,
    MemoryStats,
    NetworkStats,
    ProcessDetail,
    ProcessSummary,
    ResourceSnapshot,
)


class AgentHttpClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        opener=None,
        timeout: int = 10,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._opener = opener or request.build_opener()
        self._timeout = timeout

    def health(self) -> bool:
        return bool(self._get_json("/health").get("ok"))

    def resource_snapshot(self) -> ResourceSnapshot:
        return _snapshot_from_json(self._get_json("/resources"))

    def processes(self) -> list[ProcessSummary]:
        payload = self._get_json("/processes")
        return [_process_summary_from_json(row) for row in payload.get("processes", [])]

    def process_detail(self, pid: int) -> ProcessDetail:
        return _process_detail_from_json(self._get_json(f"/processes/{pid}"))

    def _get_json(self, path: str) -> dict[str, Any]:
        agent_request = request.Request(f"{self._base_url}{path}")
        agent_request.add_header("Authorization", f"Bearer {self._token}")
        response = self._opener.open(agent_request, timeout=self._timeout)
        return json.loads(response.read().decode("utf-8"))


def _snapshot_from_json(payload: dict[str, Any]) -> ResourceSnapshot:
    return ResourceSnapshot(
        cpu=CpuStats(percent=float(payload["cpu"]["percent"])),
        memory=MemoryStats(
            total_bytes=int(payload["memory"]["total_bytes"]),
            used_bytes=int(payload["memory"]["used_bytes"]),
            available_bytes=int(payload["memory"]["available_bytes"]),
        ),
        disks=[
            DiskUsage(
                mount=str(row["mount"]),
                total_bytes=int(row["total_bytes"]),
                used_bytes=int(row["used_bytes"]),
                available_bytes=int(row["available_bytes"]),
            )
            for row in payload.get("disks", [])
        ],
        network=NetworkStats(
            rx_bytes_per_sec=int(payload["network"]["rx_bytes_per_sec"]),
            tx_bytes_per_sec=int(payload["network"]["tx_bytes_per_sec"]),
        ),
        processes=[_process_summary_from_json(row) for row in payload.get("processes", [])],
    )


def _process_summary_from_json(payload: dict[str, Any]) -> ProcessSummary:
    return ProcessSummary(
        pid=int(payload["pid"]),
        user=str(payload["user"]),
        name=str(payload["name"]),
        cpu_percent=float(payload["cpu_percent"]),
        memory_percent=float(payload["memory_percent"]),
    )


def _process_detail_from_json(payload: dict[str, Any]) -> ProcessDetail:
    return ProcessDetail(
        pid=int(payload["pid"]),
        user=str(payload["user"]),
        name=str(payload["name"]),
        cpu_percent=float(payload["cpu_percent"]),
        memory_percent=float(payload["memory_percent"]),
        command_line=str(payload["command_line"]),
        start_time=str(payload["start_time"]),
        thread_count=int(payload["thread_count"]),
        status=str(payload["status"]),
    )
