from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from filezall_core.models import SiteProfile


class AgentTunnelHandle(Protocol):
    local_port: int

    def is_running(self) -> bool:
        ...

    def stop(self) -> None:
        ...


class AgentTunnelRunner(Protocol):
    def start(self, command: list[str]) -> AgentTunnelHandle:
        ...


@dataclass(frozen=True)
class AgentTunnelEndpoint:
    base_url: str
    local_port: int


class AgentTunnelManager:
    def __init__(self, runner: AgentTunnelRunner) -> None:
        self._runner = runner
        self._handle: AgentTunnelHandle | None = None

    def open(
        self,
        site: SiteProfile,
        local_port: int = 0,
        remote_host: str = "127.0.0.1",
        remote_port: int = 8765,
    ) -> AgentTunnelEndpoint:
        self.close()
        bind_host = "127.0.0.1"
        command = [
            "ssh",
            "-N",
            "-L",
            f"{bind_host}:{local_port}:{remote_host}:{remote_port}",
            "-p",
            str(site.port),
            f"{site.username}@{site.host}",
        ]
        self._handle = self._runner.start(command)
        return AgentTunnelEndpoint(
            base_url=f"http://{bind_host}:{self._handle.local_port}",
            local_port=self._handle.local_port,
        )

    def active(self) -> bool:
        return self._handle is not None and self._handle.is_running()

    def close(self) -> None:
        if self._handle is not None and self._handle.is_running():
            self._handle.stop()
        self._handle = None
