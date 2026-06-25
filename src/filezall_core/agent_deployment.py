from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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


class AgentInstaller:
    def __init__(self, runner: AgentDeployRunner) -> None:
        self._runner = runner

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
        return AgentInstallResult(success=True, commands_run=len(commands))
