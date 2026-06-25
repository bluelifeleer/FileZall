from __future__ import annotations

from collections.abc import Callable
from typing import Protocol as TypingProtocol

from filezall_core.models import Protocol, SiteProfile
from filezall_core.resource_models import ProcessDetail, ProcessSummary, ResourceSnapshot


class ResourceMonitoringUnavailable(RuntimeError):
    pass


class ResourceProvider(TypingProtocol):
    def snapshot(self) -> ResourceSnapshot:
        ...

    def processes(self) -> list[ProcessSummary]:
        ...

    def process_detail(self, pid: int) -> ProcessDetail | None:
        ...


class ResourceMonitorService:
    def __init__(
        self,
        agent_provider_factory: Callable[[SiteProfile], ResourceProvider],
        ssh_provider_factory: Callable[[SiteProfile], ResourceProvider] | None = None,
    ) -> None:
        self._agent_provider_factory = agent_provider_factory
        self._ssh_provider_factory = ssh_provider_factory

    def snapshot(self, site: SiteProfile) -> ResourceSnapshot:
        return self._provider_for(site).snapshot()

    def processes(self, site: SiteProfile) -> list[ProcessSummary]:
        return self._provider_for(site).processes()

    def process_detail(self, site: SiteProfile, pid: int) -> ProcessDetail | None:
        return self._provider_for(site).process_detail(pid)

    def _provider_for(self, site: SiteProfile) -> ResourceProvider:
        if site.agent_enabled:
            return self._agent_provider_factory(site)
        if site.protocol is Protocol.SFTP and self._ssh_provider_factory is not None:
            return self._ssh_provider_factory(site)
        raise ResourceMonitoringUnavailable("Resource monitoring requires SSH or FileZall Agent.")
