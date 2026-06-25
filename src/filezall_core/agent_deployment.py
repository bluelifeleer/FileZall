from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
import secrets
import shlex
import tarfile
import tempfile
import json
from typing import Protocol

import paramiko

from filezall_core.agent_client import _process_detail_from_json, _snapshot_from_json
from filezall_core.models import AuthMode, SiteProfile
from filezall_core.resource_models import ProcessDetail, ResourceSnapshot


class AgentDeployRunner(Protocol):
    def upload(self, local_path: Path, remote_path: str) -> None:
        ...

    def run(self, command: str) -> None:
        ...

    def capture(self, command: str) -> str:
        ...

    def close(self) -> None:
        ...


@dataclass(frozen=True)
class AgentInstallResult:
    success: bool
    commands_run: int
    verified: bool = False
    agent_token_ref: str | None = None


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
        env_command = _agent_env_command(token)
        commands = [
            "sudo mkdir -p /opt/filezall-agent",
            f"sudo tar -xzf {remote_package} -C /opt/filezall-agent --strip-components=1",
            env_command,
            "sudo cp /opt/filezall-agent/systemd/filezall-agent.service /etc/systemd/system/filezall-agent.service",
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


class ParamikoAgentDeployRunner:
    def __init__(self, site: SiteProfile, password: str | None = None, paramiko_module=paramiko) -> None:
        self._site = site
        self._password = password
        self._paramiko = paramiko_module
        self._ssh = None
        self._sftp = None

    def upload(self, local_path: Path, remote_path: str) -> None:
        self._connect()
        self._sftp.put(str(local_path), remote_path)

    def run(self, command: str) -> None:
        self._connect()
        self._exec(command)

    def capture(self, command: str) -> str:
        self._connect()
        stdout, _stderr = self._exec(command)
        return stdout.read().decode("utf-8", errors="replace")

    def _exec(self, command: str):
        _stdin, stdout, stderr = self._ssh.exec_command(command)
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            error = stderr.read().decode("utf-8", errors="replace").strip()
            raise RuntimeError(error or f"Remote command failed with exit status {exit_status}: {command}")
        return stdout, stderr

    def close(self) -> None:
        if self._sftp is not None:
            self._sftp.close()
            self._sftp = None
        if self._ssh is not None:
            self._ssh.close()
            self._ssh = None

    def _connect(self) -> None:
        if self._ssh is not None and self._sftp is not None:
            return
        client = self._paramiko.SSHClient()
        client.set_missing_host_key_policy(self._paramiko.AutoAddPolicy())
        kwargs = {
            "hostname": self._site.host,
            "port": self._site.port,
            "username": self._site.username,
            "timeout": 15,
        }
        if self._site.auth_mode == AuthMode.PASSWORD:
            kwargs["password"] = self._password
        elif self._site.auth_mode == AuthMode.SSH_KEY:
            if self._site.ssh_key_path is None:
                raise RuntimeError("SSH key path is required for Agent installation")
            kwargs["key_filename"] = str(self._site.ssh_key_path)
            if self._password:
                kwargs["passphrase"] = self._password
        client.connect(**kwargs)
        self._ssh = client
        self._sftp = client.open_sftp()


class AgentDeploymentService:
    def __init__(
        self,
        *,
        package_builder: Callable[[], Path],
        runner_factory: Callable[[SiteProfile, str | None], AgentDeployRunner],
        credential_service,
        site_repository,
        token_factory: Callable[[], str] | None = None,
    ) -> None:
        self._package_builder = package_builder
        self._runner_factory = runner_factory
        self._credential_service = credential_service
        self._site_repository = site_repository
        self._token_factory = token_factory or (lambda: secrets.token_urlsafe(32))

    def install(self, site: SiteProfile, password: str | None = None) -> AgentInstallResult:
        token = self._token_factory()
        runner = self._runner_factory(site, password)
        try:
            installer = AgentInstaller(
                runner,
                health_check=lambda: _remote_health_check(runner, token),
            )
            result = installer.install_or_update(self._package_builder(), token)
        finally:
            runner.close()
        if not result.success:
            return result
        token_ref = self._credential_service.save_secret(site.id, "agent-token", token)
        self._site_repository.save(
            _replace_agent_state(site, enabled=True, token_ref=token_ref),
        )
        return AgentInstallResult(
            success=True,
            commands_run=result.commands_run,
            verified=result.verified,
            agent_token_ref=token_ref,
        )

    def uninstall(self, site: SiteProfile, password: str | None = None) -> AgentInstallResult:
        runner = self._runner_factory(site, password)
        try:
            result = AgentInstaller(runner).uninstall()
        finally:
            runner.close()
        if result.success:
            self._credential_service.delete_secret(site.agent_token_ref)
            self._site_repository.save(
                _replace_agent_state(site, enabled=False, token_ref=None),
            )
        return result

    def resource_snapshot(self, site: SiteProfile, password: str | None = None) -> ResourceSnapshot:
        return _snapshot_from_json(self._agent_get_json(site, password, "/resources"))

    def process_detail(
        self,
        site: SiteProfile,
        pid: int,
        password: str | None = None,
    ) -> ProcessDetail:
        return _process_detail_from_json(self._agent_get_json(site, password, f"/processes/{pid}"))

    def _agent_get_json(self, site: SiteProfile, password: str | None, path: str) -> dict:
        token = self._credential_service.get_secret(site.agent_token_ref)
        if not token:
            raise RuntimeError("Agent token is not available for this site")
        runner = self._runner_factory(site, password)
        try:
            return json.loads(runner.capture(self.agent_get_command(token, path)))
        finally:
            runner.close()

    @staticmethod
    def agent_get_command(token: str, path: str) -> str:
        code = _agent_get_code(token, path)
        return f"python3 -c {shlex.quote(code)}"


def build_agent_package(agent_root: Path, output_dir: Path | None = None) -> Path:
    output_dir = output_dir or Path(tempfile.gettempdir())
    output_dir.mkdir(parents=True, exist_ok=True)
    package_path = output_dir / "filezall-agent.tar.gz"
    with tarfile.open(package_path, "w:gz") as archive:
        for child_name in ("filezall_agent", "systemd", "env"):
            source = agent_root / child_name
            if source.exists():
                _add_tree(archive, source, Path("filezall-agent") / child_name)
    return package_path


def _add_tree(archive: tarfile.TarFile, source: Path, arc_root: Path) -> None:
    for path in source.rglob("*"):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        archive.add(path, arcname=str(arc_root / path.relative_to(source)))


def _agent_env_command(token: str) -> str:
    lines = [
        f"FILEZALL_AGENT_TOKEN={token}",
        "FILEZALL_AGENT_HOST=127.0.0.1",
        "FILEZALL_AGENT_PORT=8765",
    ]
    quoted_lines = " ".join(_single_quote(line) for line in lines)
    return (
        "printf '%s\\n' "
        f"{quoted_lines} | sudo tee /opt/filezall-agent/agent.env >/dev/null"
    )


def _remote_health_check(runner: AgentDeployRunner, token: str) -> bool:
    try:
        runner.run(AgentDeploymentService.agent_get_command(token, "/health"))
    except Exception:
        return False
    return True


def _agent_get_code(token: str, path: str) -> str:
    return (
        "import json,urllib.request;"
        "req=urllib.request.Request("
        f"{'http://127.0.0.1:8765' + path!r},"
        f"headers={{'Authorization': {'Bearer ' + token!r}}}"
        ");"
        "print(urllib.request.urlopen(req,timeout=10).read().decode('utf-8'))"
    )


def _single_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def _replace_agent_state(site: SiteProfile, *, enabled: bool, token_ref: str | None) -> SiteProfile:
    from dataclasses import replace

    return replace(site, agent_enabled=enabled, agent_token_ref=token_ref)
