from pathlib import Path

from filezall_core.agent_deployment import (
    AgentDeploymentService,
    AgentInstaller,
    build_agent_package,
    classify_agent_error,
)
from filezall_core.models import AuthMode, Protocol, SiteProfile


class FakeRunner:
    def __init__(self) -> None:
        self.uploads = []
        self.commands = []
        self.captures = []
        self.capture_payloads = {}

    def upload(self, local_path: Path, remote_path: str) -> None:
        self.uploads.append((local_path, remote_path))

    def run(self, command: str) -> None:
        self.commands.append(command)

    def capture(self, command: str) -> str:
        self.captures.append(command)
        return self.capture_payloads.get(command, "{}")

    def close(self) -> None:
        self.closed = True


class FakeCredentials:
    def __init__(self) -> None:
        self.saved = []
        self.deleted = []
        self.secrets = {}

    def save_secret(self, site_id: str, purpose: str, secret: str) -> str:
        self.saved.append((site_id, purpose, secret))
        ref = f"{site_id}:{purpose}"
        self.secrets[ref] = secret
        return ref

    def delete_secret(self, ref: str | None) -> None:
        self.deleted.append(ref)

    def get_secret(self, ref: str | None) -> str | None:
        return self.secrets.get(ref)


class FakeRepository:
    def __init__(self) -> None:
        self.saved = []

    def save(self, site) -> None:
        self.saved.append(site)


def test_agent_installer_uploads_package_and_runs_install_commands(tmp_path: Path) -> None:
    runner = FakeRunner()
    installer = AgentInstaller(runner)
    package = tmp_path / "filezall-agent.tar.gz"
    package.write_bytes(b"agent")

    result = installer.install_or_update(package, token="secret-token")

    assert runner.uploads == [(package, "/tmp/filezall-agent.tar.gz")]
    assert runner.commands == [
        "sudo mkdir -p /opt/filezall-agent",
        "sudo tar -xzf /tmp/filezall-agent.tar.gz -C /opt/filezall-agent --strip-components=1",
        "printf '%s\\n' 'FILEZALL_AGENT_TOKEN=secret-token' 'FILEZALL_AGENT_HOST=127.0.0.1' 'FILEZALL_AGENT_PORT=8765' | sudo tee /opt/filezall-agent/agent.env >/dev/null",
        "sudo cp /opt/filezall-agent/systemd/filezall-agent.service /etc/systemd/system/filezall-agent.service",
        "sudo systemctl daemon-reload",
        "sudo systemctl enable filezall-agent",
        "sudo systemctl restart filezall-agent",
        "systemctl is-active --quiet filezall-agent",
    ]
    assert result.success is True
    assert result.verified is False
    assert result.commands_run == len(runner.commands)


def test_agent_installer_marks_install_verified_when_health_check_passes(tmp_path: Path) -> None:
    runner = FakeRunner()
    installer = AgentInstaller(runner, health_check=lambda: True)
    package = tmp_path / "filezall-agent.tar.gz"
    package.write_bytes(b"agent")

    result = installer.install_or_update(package, token="secret-token")

    assert result.success is True
    assert result.verified is True


def test_agent_installer_reports_install_progress(tmp_path: Path) -> None:
    runner = FakeRunner()
    messages = []
    installer = AgentInstaller(
        runner,
        health_check=lambda: True,
        progress_callback=messages.append,
    )
    package = tmp_path / "filezall-agent.tar.gz"
    package.write_bytes(b"agent")

    result = installer.install_or_update(package, token="secret-token")

    assert result.verified is True
    assert "Agent install: uploading package" in messages
    assert "Agent install: extracting package" in messages
    assert "Agent install: checking service status" in messages
    assert "Agent install: checking health endpoint" in messages
    assert "Agent install: health check passed" in messages


def test_agent_installer_reports_failure_when_health_check_fails(tmp_path: Path) -> None:
    runner = FakeRunner()
    installer = AgentInstaller(runner, health_check=lambda: False)
    package = tmp_path / "filezall-agent.tar.gz"
    package.write_bytes(b"agent")

    result = installer.install_or_update(package, token="secret-token")

    assert result.success is False
    assert result.verified is False


def test_agent_error_classifier_returns_operator_guidance() -> None:
    assert classify_agent_error("sudo: a password is required") == (
        "Permission denied while managing FileZall Agent. Connect as a sudo-capable user or configure passwordless sudo for Agent install commands."
    )
    assert classify_agent_error("System has not been booted with systemd as init system") == (
        "This server does not appear to support systemd. FileZall Agent currently requires a systemd-based Linux host."
    )
    assert classify_agent_error("OSError: [Errno 98] Address already in use") == (
        "FileZall Agent port 8765 is already in use. Stop the conflicting service or reinstall Agent after freeing the port."
    )
    assert classify_agent_error("Agent install: health check failed") == (
        "FileZall Agent service started, but the health endpoint did not respond. Check firewall rules, localhost access, and filezall-agent service logs."
    )


def test_agent_installer_uninstalls_systemd_service() -> None:
    runner = FakeRunner()
    installer = AgentInstaller(runner)

    result = installer.uninstall()

    assert runner.commands == [
        "sudo systemctl stop filezall-agent || true",
        "sudo systemctl disable filezall-agent || true",
        "sudo rm -f /etc/systemd/system/filezall-agent.service",
        "sudo systemctl daemon-reload",
        "sudo rm -rf /opt/filezall-agent",
    ]
    assert result.success is True
    assert result.commands_run == len(runner.commands)


def test_build_agent_package_contains_runtime_and_systemd_files(tmp_path: Path) -> None:
    agent_root = tmp_path / "agent"
    (agent_root / "filezall_agent").mkdir(parents=True)
    (agent_root / "filezall_agent" / "server.py").write_text("print('agent')", encoding="utf-8")
    (agent_root / "filezall_agent" / "__pycache__").mkdir()
    (agent_root / "filezall_agent" / "__pycache__" / "server.pyc").write_bytes(b"pyc")
    (agent_root / "systemd").mkdir()
    (agent_root / "systemd" / "filezall-agent.service").write_text("[Service]", encoding="utf-8")
    (agent_root / "env").mkdir()
    (agent_root / "env" / "filezall-agent.env.example").write_text("TOKEN=", encoding="utf-8")

    package = build_agent_package(agent_root, tmp_path / "out")

    import tarfile

    with tarfile.open(package, "r:gz") as archive:
        names = set(archive.getnames())
    assert "filezall-agent/filezall_agent/server.py" in names
    assert "filezall-agent/systemd/filezall-agent.service" in names
    assert "filezall-agent/env/filezall-agent.env.example" in names
    assert "filezall-agent/filezall_agent/__pycache__/server.pyc" not in names


def test_agent_deployment_service_installs_and_marks_site_agent_enabled(tmp_path: Path) -> None:
    runner = FakeRunner()
    credentials = FakeCredentials()
    repository = FakeRepository()
    package = tmp_path / "filezall-agent.tar.gz"
    package.write_bytes(b"agent")
    service = AgentDeploymentService(
        package_builder=lambda: package,
        runner_factory=lambda site, password: runner,
        credential_service=credentials,
        site_repository=repository,
        token_factory=lambda: "generated-token",
    )
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )

    result = service.install(site, password="secret")

    assert result.success is True
    assert result.verified is True
    assert result.agent_token_ref == "site-1:agent-token"
    assert credentials.saved == [("site-1", "agent-token", "generated-token")]
    assert repository.saved[-1].agent_enabled is True
    assert repository.saved[-1].agent_token_ref == "site-1:agent-token"
    assert any("/health" in command for command in runner.commands)


def test_agent_deployment_service_reports_high_level_install_progress(tmp_path: Path) -> None:
    runner = FakeRunner()
    credentials = FakeCredentials()
    repository = FakeRepository()
    package = tmp_path / "filezall-agent.tar.gz"
    package.write_bytes(b"agent")
    messages = []
    service = AgentDeploymentService(
        package_builder=lambda: package,
        runner_factory=lambda site, password: runner,
        credential_service=credentials,
        site_repository=repository,
        token_factory=lambda: "generated-token",
    )

    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )

    result = service.install(site, password="secret", progress_callback=messages.append)

    assert result.success is True
    assert "Agent install: opening SSH session" in messages
    assert "Agent install: building local package" in messages
    assert "Agent install: saving Agent token" in messages


def test_agent_deployment_service_uninstalls_and_clears_agent_flag() -> None:
    runner = FakeRunner()
    credentials = FakeCredentials()
    repository = FakeRepository()
    service = AgentDeploymentService(
        package_builder=lambda: Path("unused.tar.gz"),
        runner_factory=lambda site, password: runner,
        credential_service=credentials,
        site_repository=repository,
        token_factory=lambda: "generated-token",
    )
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
        agent_enabled=True,
        agent_token_ref="site-1:agent-token",
    )

    result = service.uninstall(site, password="secret")

    assert result.success is True
    assert credentials.deleted == ["site-1:agent-token"]
    assert repository.saved[-1].agent_enabled is False
    assert repository.saved[-1].agent_token_ref is None


def test_agent_deployment_service_detects_installed_agent_service() -> None:
    runner = FakeRunner()
    credentials = FakeCredentials()
    repository = FakeRepository()
    messages = []
    service = AgentDeploymentService(
        package_builder=lambda: Path("unused.tar.gz"),
        runner_factory=lambda site, password: runner,
        credential_service=credentials,
        site_repository=repository,
        token_factory=lambda: "generated-token",
    )
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )

    installed = service.is_agent_installed(
        site,
        password="secret",
        progress_callback=messages.append,
    )

    assert installed is True
    assert runner.commands == [
        "test -d /opt/filezall-agent "
        "-o -f /etc/systemd/system/filezall-agent.service "
        "-o -f /lib/systemd/system/filezall-agent.service"
    ]
    assert "Agent detection: service installed" in messages


def test_agent_deployment_service_imports_detected_agent_token() -> None:
    runner = FakeRunner()
    runner.capture_payloads["cat /opt/filezall-agent/agent.env"] = (
        "FILEZALL_AGENT_TOKEN=stored-token\n"
        "FILEZALL_AGENT_HOST=127.0.0.1\n"
    )
    runner.capture_payloads[
        AgentDeploymentService.agent_get_command("stored-token", "/health")
    ] = '{"ok":true,"version":"0.1.0","api_version":1}'
    credentials = FakeCredentials()
    repository = FakeRepository()
    service = AgentDeploymentService(
        package_builder=lambda: Path("unused.tar.gz"),
        runner_factory=lambda site, password: runner,
        credential_service=credentials,
        site_repository=repository,
        token_factory=lambda: "generated-token",
    )
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )

    result = service.detect_agent_installation(site, password="secret")

    assert result.installed is True
    assert result.agent_token_ref == "site-1:agent-token"
    assert result.agent_version == "0.1.0"
    assert credentials.saved == [("site-1", "agent-token", "stored-token")]
    assert repository.saved[-1].agent_enabled is True
    assert repository.saved[-1].agent_token_ref == "site-1:agent-token"


def test_agent_deployment_service_reports_agent_service_missing() -> None:
    class MissingAgentRunner(FakeRunner):
        def run(self, command: str) -> None:
            super().run(command)
            raise RuntimeError("missing")

    runner = MissingAgentRunner()
    credentials = FakeCredentials()
    repository = FakeRepository()
    messages = []
    service = AgentDeploymentService(
        package_builder=lambda: Path("unused.tar.gz"),
        runner_factory=lambda site, password: runner,
        credential_service=credentials,
        site_repository=repository,
        token_factory=lambda: "generated-token",
    )
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )

    installed = service.is_agent_installed(
        site,
        password="secret",
        progress_callback=messages.append,
    )

    assert installed is False
    assert "Agent detection: service not installed" in messages


def test_agent_deployment_service_reads_resource_snapshot_through_remote_agent() -> None:
    runner = FakeRunner()
    credentials = FakeCredentials()
    credentials.secrets["site-1:agent-token"] = "stored-token"
    repository = FakeRepository()
    runner.capture_payloads = {
        command: payload
        for command, payload in [
            (
                AgentDeploymentService.agent_get_command("stored-token", "/resources"),
                '{"cpu":{"percent":12.5},"memory":{"total_bytes":1000,"used_bytes":400,"available_bytes":600},"disks":[],"network":{"rx_bytes_per_sec":1,"tx_bytes_per_sec":2},"processes":[]}',
            )
        ]
    }
    service = AgentDeploymentService(
        package_builder=lambda: Path("unused.tar.gz"),
        runner_factory=lambda site, password: runner,
        credential_service=credentials,
        site_repository=repository,
        token_factory=lambda: "generated-token",
    )
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
        agent_enabled=True,
        agent_token_ref="site-1:agent-token",
    )

    snapshot = service.resource_snapshot(site, password="secret")

    assert snapshot.cpu.percent == 12.5
    assert snapshot.memory.used_bytes == 400
    assert runner.captures == [AgentDeploymentService.agent_get_command("stored-token", "/resources")]


def test_agent_deployment_service_sends_process_signals_over_ssh() -> None:
    runner = FakeRunner()
    credentials = FakeCredentials()
    repository = FakeRepository()
    service = AgentDeploymentService(
        package_builder=lambda: Path("unused.tar.gz"),
        runner_factory=lambda site, password: runner,
        credential_service=credentials,
        site_repository=repository,
        token_factory=lambda: "generated-token",
    )
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )

    service.signal_process(site, 123, "TERM", password="secret")
    service.signal_process(site, 123, "HUP", password="secret")

    assert runner.commands == ["kill -TERM 123", "kill -HUP 123"]
