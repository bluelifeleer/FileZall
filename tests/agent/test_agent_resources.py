from pathlib import Path

from filezall_agent.resources import (
    AgentResourceService,
    parse_meminfo,
    parse_net_dev,
    parse_proc_stat,
)


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


def test_parse_net_dev_returns_total_non_loopback_bytes() -> None:
    net_dev = """
Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo: 100 1 0 0 0 0 0 0 200 1 0 0 0 0 0 0
  eth0: 1024 8 0 0 0 0 0 0 2048 9 0 0 0 0 0 0
  ens5: 4096 4 0 0 0 0 0 0 8192 5 0 0 0 0 0 0
"""

    assert parse_net_dev(net_dev) == {"rx_bytes": 5120, "tx_bytes": 10240}


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


def test_agent_resource_service_reports_cpu_after_two_proc_stat_samples(tmp_path: Path) -> None:
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    (proc_root / "stat").write_text("cpu  100 0 100 800 0 0 0 0 0 0\n", encoding="utf-8")
    (proc_root / "meminfo").write_text(
        "MemTotal: 1000 kB\nMemAvailable: 500 kB\n",
        encoding="utf-8",
    )
    service = AgentResourceService(proc_root=proc_root)

    first = service.resources()
    (proc_root / "stat").write_text("cpu  150 0 150 900 0 0 0 0 0 0\n", encoding="utf-8")
    second = service.resources()

    assert first["cpu"]["percent"] == 0.0
    assert second["cpu"]["percent"] == 50.0


def test_agent_resource_service_reports_cpu_on_first_resource_after_start(tmp_path: Path) -> None:
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    (proc_root / "stat").write_text("cpu  100 0 100 800 0 0 0 0 0 0\n", encoding="utf-8")
    (proc_root / "meminfo").write_text(
        "MemTotal: 1000 kB\nMemAvailable: 500 kB\n",
        encoding="utf-8",
    )
    service = AgentResourceService(proc_root=proc_root)

    (proc_root / "stat").write_text("cpu  150 0 150 900 0 0 0 0 0 0\n", encoding="utf-8")
    snapshot = service.resources()

    assert snapshot["cpu"]["percent"] == 50.0


def test_agent_resource_service_reports_network_rates_between_samples(tmp_path: Path) -> None:
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    net_dir = proc_root / "net"
    net_dir.mkdir()
    (proc_root / "stat").write_text("cpu  100 0 100 800 0 0 0 0 0 0\n", encoding="utf-8")
    (proc_root / "meminfo").write_text(
        "MemTotal: 1000 kB\nMemAvailable: 500 kB\n",
        encoding="utf-8",
    )
    (net_dir / "dev").write_text(_net_dev(rx=1000, tx=2000), encoding="utf-8")
    clock_values = iter([10.0, 12.0])
    service = AgentResourceService(proc_root=proc_root, clock=lambda: next(clock_values))

    (net_dir / "dev").write_text(_net_dev(rx=3000, tx=7000), encoding="utf-8")
    snapshot = service.resources()

    assert snapshot["network"] == {"rx_bytes_per_sec": 1000, "tx_bytes_per_sec": 2500}


def _net_dev(*, rx: int, tx: int) -> str:
    return f"""
Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
  eth0: {rx} 8 0 0 0 0 0 0 {tx} 9 0 0 0 0 0 0
"""
