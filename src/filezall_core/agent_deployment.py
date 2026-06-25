from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Protocol


class AgentDeployRunner(Protocol):
    def upload(self, local_path: Path, remote_path: str) -> None:
        ...

    def run(self, command: str) -> None:
        ...


@dataclass(frozen=True)
class AgentInstallResult:
    success: bool
    commands_run: int
    verified: bool = False


class AgentInstaller:
    def __init__(
        self,
        runner: AgentDeployRunner,
        health_check: Callable[[], bool] | None = None,
    ) -> None:
        self._runner = runner
        self._health_check = health_check

    def install_or_update(self, package_path: Path, token: str) -> AgentInstallResult:
        remote_package = "/tmp/filezall-agent.tar.gz"
        self._runner.upload(package_path, remote_package)
        commands = [
            "sudo mkdir -p /opt/filezall-agent",
            f"sudo tar -xzf {remote_package} -C /opt/filezall-agent",
            f"printf '%s' 'FILEZALL_AGENT_TOKEN={token}' | sudo tee /opt/filezall-agent/agent.env >/dev/null",
            "sudo cp /opt/filezall-agent/filezall-agent.service /etc/systemd/system/filezall-agent.service",
            "sudo systemctl daemon-reload",
            "sudo systemctl enable filezall-agent",
            "sudo systemctl restart filezall-agent",
            "systemctl is-active --quiet filezall-agent",
        ]
        for command in commands:
            self._runner.run(command)
        if self._health_check is None:
            return AgentInstallResult(success=True, commands_run=len(commands))
        verified = self._health_check()
        return AgentInstallResult(
            success=verified,
            commands_run=len(commands),
            verified=verified,
        )

    def uninstall(self) -> AgentInstallResult:
        commands = [
            "sudo systemctl stop filezall-agent || true",
            "sudo systemctl disable filezall-agent || true",
            "sudo rm -f /etc/systemd/system/filezall-agent.service",
            "sudo systemctl daemon-reload",
            "sudo rm -rf /opt/filezall-agent",
        ]
        for command in commands:
            self._runner.run(command)
        return AgentInstallResult(success=True, commands_run=len(commands))
