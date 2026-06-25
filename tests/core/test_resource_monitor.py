import pytest

from filezall_core.models import AuthMode, Protocol, SiteProfile
from filezall_core.resource_models import (
    CpuStats,
    MemoryStats,
    NetworkStats,
    ResourceSnapshot,
)
from filezall_core.resource_monitor import ResourceMonitoringUnavailable, ResourceMonitorService


class FakeProvider:
    def __init__(self) -> None:
        self.snapshot_calls = 0
        self.process_calls = 0
        self.detail_calls = []

    def snapshot(self) -> ResourceSnapshot:
        self.snapshot_calls += 1
        return ResourceSnapshot(
            cpu=CpuStats(percent=12.5),
            memory=MemoryStats(total_bytes=1000, used_bytes=400, available_bytes=600),
            disks=[],
            network=NetworkStats(rx_bytes_per_sec=1, tx_bytes_per_sec=2),
            processes=[],
        )

    def processes(self):
        self.process_calls += 1
        return []

    def process_detail(self, pid: int):
        self.detail_calls.append(pid)
        return None


def test_resource_monitor_delegates_agent_enabled_site_to_agent_provider() -> None:
    agent_provider = FakeProvider()
    service = ResourceMonitorService(
        agent_provider_factory=lambda site: agent_provider,
        ssh_provider_factory=lambda site: FakeProvider(),
    )
    site = _site(Protocol.SFTP, agent_enabled=True)

    snapshot = service.snapshot(site)
    service.processes(site)
    service.process_detail(site, 123)

    assert snapshot.cpu.percent == 12.5
    assert agent_provider.snapshot_calls == 1
    assert agent_provider.process_calls == 1
    assert agent_provider.detail_calls == [123]


def test_resource_monitor_uses_ssh_provider_for_sftp_without_agent() -> None:
    ssh_provider = FakeProvider()
    service = ResourceMonitorService(
        agent_provider_factory=lambda site: FakeProvider(),
        ssh_provider_factory=lambda site: ssh_provider,
    )

    service.snapshot(_site(Protocol.SFTP))

    assert ssh_provider.snapshot_calls == 1


def test_resource_monitor_rejects_ftp_without_agent() -> None:
    service = ResourceMonitorService(agent_provider_factory=lambda site: FakeProvider())

    with pytest.raises(ResourceMonitoringUnavailable, match="requires SSH or FileZall Agent"):
        service.snapshot(_site(Protocol.FTP))


def _site(protocol: Protocol, agent_enabled: bool = False) -> SiteProfile:
    return SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=protocol,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
        agent_enabled=agent_enabled,
    )
