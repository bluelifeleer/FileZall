from pathlib import Path

from filezall_agent.resources import AgentResourceService, parse_meminfo, parse_proc_stat


def test_parse_meminfo_returns_expected_bytes() -> None:
    meminfo = """
MemTotal:       1000 kB
MemFree:         200 kB
MemAvailable:    600 kB
Buffers:          50 kB
Cached:          100 kB
"""

    memory = parse_meminfo(meminfo)

    assert memory == {"total_bytes": 1024000, "used_bytes": 409600, "available_bytes": 614400}


def test_parse_proc_stat_returns_cpu_percent_between_samples() -> None:
    previous = "cpu  100 0 100 800 0 0 0 0 0 0"
    current = "cpu  150 0 150 900 0 0 0 0 0 0"

    assert parse_proc_stat(previous, current) == 50.0


def test_agent_resource_service_returns_snapshot_shape(tmp_path: Path) -> None:
    service = AgentResourceService(proc_root=tmp_path / "missing-proc")

    snapshot = service.resources()
    processes = service.processes()
    detail = service.process_detail(123)

    assert snapshot["cpu"]["percent"] == 0.0
    assert snapshot["memory"]["total_bytes"] == 0
    assert snapshot["disks"][0]["mount"]
    assert snapshot["network"] == {"rx_bytes_per_sec": 0, "tx_bytes_per_sec": 0}
    assert snapshot["processes"] == []
    assert processes == {"processes": []}
    assert detail["pid"] == 123
    assert detail["status"] == "unknown"
