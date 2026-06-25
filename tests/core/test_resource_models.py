from filezall_core.resource_models import (
    CpuStats,
    DiskUsage,
    MemoryStats,
    NetworkStats,
    ProcessDetail,
    ProcessSummary,
    ResourceSnapshot,
)


def test_resource_snapshot_models_round_trip_fields() -> None:
    cpu = CpuStats(percent=12.5)
    memory = MemoryStats(total_bytes=1000, used_bytes=400, available_bytes=600)
    disk = DiskUsage(mount="/", total_bytes=2000, used_bytes=1000, available_bytes=1000)
    network = NetworkStats(rx_bytes_per_sec=10, tx_bytes_per_sec=20)
    process = ProcessSummary(pid=123, user="deploy", name="python", cpu_percent=1.5, memory_percent=2.5)
    snapshot = ResourceSnapshot(
        cpu=cpu,
        memory=memory,
        disks=[disk],
        network=network,
        processes=[process],
    )

    assert snapshot.cpu.percent == 12.5
    assert snapshot.memory.available_bytes == 600
    assert snapshot.disks[0].mount == "/"
    assert snapshot.network.tx_bytes_per_sec == 20
    assert snapshot.processes[0].pid == 123


def test_process_detail_extends_process_summary_fields() -> None:
    detail = ProcessDetail(
        pid=123,
        user="deploy",
        name="python",
        cpu_percent=1.5,
        memory_percent=2.5,
        command_line="python app.py",
        start_time="2026-06-25T12:00:00Z",
        thread_count=8,
        status="sleeping",
    )

    assert detail.command_line == "python app.py"
    assert detail.thread_count == 8
    assert detail.status == "sleeping"
