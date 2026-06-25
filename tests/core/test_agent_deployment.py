from pathlib import Path

from filezall_core.agent_deployment import AgentInstaller


class FakeRunner:
    def __init__(self) -> None:
        self.uploads = []
        self.commands = []

    def upload(self, local_path: Path, remote_path: str) -> None:
        self.uploads.append((local_path, remote_path))

    def run(self, command: str) -> None:
        self.commands.append(command)


def test_agent_installer_uploads_package_and_runs_install_commands(tmp_path: Path) -> None:
    runner = FakeRunner()
    installer = AgentInstaller(runner)
    package = tmp_path / "filezall-agent.tar.gz"
    package.write_bytes(b"agent")

    result = installer.install_or_update(package, token="secret-token")

    assert runner.uploads == [(package, "/tmp/filezall-agent.tar.gz")]
    assert runner.commands == [
        "sudo mkdir -p /opt/filezall-agent",
        "sudo tar -xzf /tmp/filezall-agent.tar.gz -C /opt/filezall-agent",
        "printf '%s' 'FILEZALL_AGENT_TOKEN=secret-token' | sudo tee /opt/filezall-agent/agent.env >/dev/null",
        "sudo cp /opt/filezall-agent/filezall-agent.service /etc/systemd/system/filezall-agent.service",
        "sudo systemctl daemon-reload",
        "sudo systemctl enable filezall-agent",
        "sudo systemctl restart filezall-agent",
        "systemctl is-active --quiet filezall-agent",
    ]
    assert result.success is True
    assert result.commands_run == len(runner.commands)
