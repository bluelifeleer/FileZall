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


@dataclass(frozen=True)
class AgentDetectionResult:
    installed: bool
    commands_run: int
    agent_token_ref: str | None = None
    agent_version: str | None = None


class AgentInstaller:
    def __init__(
        self,
        runner: AgentDeployRunner,
        health_check: Callable[[], bool] | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> None:
        self._runner = runner
        self._health_check = health_check
        self._progress_callback = progress_callback

    def install_or_update(self, package_path: Path, token: str) -> AgentInstallResult:
        remote_package = "/tmp/filezall-agent.tar.gz"
        self._progress("Agent install: uploading package")
        self._runner.upload(package_path, remote_package)
        env_command = _agent_env_command(token)
        commands = [
            ("creating install directory", "sudo mkdir -p /opt/filezall-agent"),
            (
                "extracting package",
                f"sudo tar -xzf {remote_package} -C /opt/filezall-agent --strip-components=1",
            ),
            ("writing environment", env_command),
            (
                "installing systemd service",
                "sudo cp /opt/filezall-agent/systemd/filezall-agent.service /etc/systemd/system/filezall-agent.service",
            ),
            ("reloading systemd", "sudo systemctl daemon-reload"),
            ("enabling service", "sudo systemctl enable filezall-agent"),
            ("restarting service", "sudo systemctl restart filezall-agent"),
            ("checking service status", "systemctl is-active --quiet filezall-agent"),
        ]
        for label, command in commands:
            self._progress(f"Agent install: {label}")
            self._runner.run(command)
        if self._health_check is None:
            return AgentInstallResult(success=True, commands_run=len(commands))
        self._progress("Agent install: checking health endpoint")
        verified = self._health_check()
        self._progress(
            "Agent install: health check passed"
            if verified
            else "Agent install: health check failed"
        )
        return AgentInstallResult(
            success=verified,
            commands_run=len(commands),
            verified=verified,
        )

    def uninstall(self) -> AgentInstallResult:
        commands = [
            ("stopping service", "sudo systemctl stop filezall-agent || true"),
            ("disabling service", "sudo systemctl disable filezall-agent || true"),
            (
                "removing systemd service",
                "sudo rm -f /etc/systemd/system/filezall-agent.service",
            ),
            ("reloading systemd", "sudo systemctl daemon-reload"),
            ("removing install directory", "sudo rm -rf /opt/filezall-agent"),
        ]
        for label, command in commands:
            self._progress(f"Agent uninstall: {label}")
            self._runner.run(command)
        return AgentInstallResult(success=True, commands_run=len(commands))

    def _progress(self, message: str) -> None:
        if self._progress_callback is not None:
            self._progress_callback(message)


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

    def install(
        self,
        site: SiteProfile,
        password: str | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> AgentInstallResult:
        token = self._token_factory()
        _progress(progress_callback, "Agent install: opening SSH session")
        runner = self._runner_factory(site, password)
        try:
            _progress(progress_callback, "Agent install: building local package")
            package_path = self._package_builder()
            installer = AgentInstaller(
                runner,
                health_check=lambda: _remote_health_check(runner, token),
                progress_callback=progress_callback,
            )
            result = installer.install_or_update(package_path, token)
        finally:
            runner.close()
        if not result.success:
            return result
        _progress(progress_callback, "Agent install: saving Agent token")
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

    def uninstall(
        self,
        site: SiteProfile,
        password: str | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> AgentInstallResult:
        _progress(progress_callback, "Agent uninstall: opening SSH session")
        runner = self._runner_factory(site, password)
        try:
            result = AgentInstaller(runner, progress_callback=progress_callback).uninstall()
        finally:
            runner.close()
        if result.success:
            _progress(progress_callback, "Agent uninstall: clearing saved Agent token")
            self._credential_service.delete_secret(site.agent_token_ref)
            self._site_repository.save(
                _replace_agent_state(site, enabled=False, token_ref=None),
            )
        return result

    def is_agent_installed(
        self,
        site: SiteProfile,
        password: str | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> bool:
        return self.detect_agent_installation(
            site,
            password,
            progress_callback=progress_callback,
        ).installed

    def detect_agent_installation(
        self,
        site: SiteProfile,
        password: str | None = None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> AgentDetectionResult:
        _progress(progress_callback, "Agent detection: opening SSH session")
        runner = self._runner_factory(site, password)
        commands_run = 0
        try:
            _progress(progress_callback, "Agent detection: checking installed service")
            runner.run(
                "test -d /opt/filezall-agent "
                "-o -f /etc/systemd/system/filezall-agent.service "
                "-o -f /lib/systemd/system/filezall-agent.service"
            )
            commands_run += 1
        except Exception:
            _progress(progress_callback, "Agent detection: service not installed")
            runner.close()
            return AgentDetectionResult(installed=False, commands_run=commands_run)
        _progress(progress_callback, "Agent detection: service installed")
        token_ref = self._saved_or_imported_agent_token(
            site,
            runner,
            progress_callback=progress_callback,
        )
        agent_version = self._agent_version_from_health(
            runner,
            token_ref,
            progress_callback=progress_callback,
        )
        runner.close()
        if token_ref is not None:
            self._site_repository.save(
                _replace_agent_state(site, enabled=True, token_ref=token_ref),
            )
            _progress(progress_callback, "Agent detection: saved Agent token")
        else:
            _progress(progress_callback, "Agent detection: Agent token not available")
        return AgentDetectionResult(
            installed=True,
            commands_run=commands_run,
            agent_token_ref=token_ref,
            agent_version=agent_version,
        )

    def _saved_or_imported_agent_token(
        self,
        site: SiteProfile,
        runner: AgentDeployRunner,
        progress_callback: Callable[[str], None] | None = None,
    ) -> str | None:
        if site.agent_token_ref and self._credential_service.get_secret(site.agent_token_ref):
            return site.agent_token_ref
        _progress(progress_callback, "Agent detection: reading Agent token")
        try:
            token = _token_from_env(runner.capture("cat /opt/filezall-agent/agent.env"))
        except Exception:
            return None
        if not token:
            return None
        return self._credential_service.save_secret(site.id, "agent-token", token)

    def _agent_version_from_health(
        self,
        runner: AgentDeployRunner,
        token_ref: str | None,
        progress_callback: Callable[[str], None] | None = None,
    ) -> str | None:
        token = self._credential_service.get_secret(token_ref)
        if not token:
            return None
        _progress(progress_callback, "Agent detection: reading Agent health")
        try:
            payload = json.loads(runner.capture(self.agent_get_command(token, "/health")))
        except Exception:
            _progress(progress_callback, "Agent detection: Agent health unavailable")
            return None
        version = payload.get("version")
        if version:
            _progress(progress_callback, f"Agent detection: Agent version {version}")
            return str(version)
        return None

    def resource_snapshot(
        self,
        site: SiteProfile,
        password: str | None = None,
        runner: AgentDeployRunner | None = None,
    ) -> ResourceSnapshot:
        return _snapshot_from_json(self._agent_get_json(site, password, "/resources", runner=runner))

    def process_detail(
        self,
        site: SiteProfile,
        pid: int,
        password: str | None = None,
        runner: AgentDeployRunner | None = None,
    ) -> ProcessDetail:
        return _process_detail_from_json(
            self._agent_get_json(site, password, f"/processes/{pid}", runner=runner)
        )

    def _agent_get_json(
        self,
        site: SiteProfile,
        password: str | None,
        path: str,
        runner: AgentDeployRunner | None = None,
    ) -> dict:
        token = self._credential_service.get_secret(site.agent_token_ref)
        if not token:
            raise RuntimeError("Agent token is not available for this site")
        owns_runner = runner is None
        runner = runner or self._runner_factory(site, password)
        try:
            return json.loads(runner.capture(self.agent_get_command(token, path)))
        finally:
            if owns_runner:
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


def _progress(callback: Callable[[str], None] | None, message: str) -> None:
    if callback is not None:
        callback(message)


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


def _token_from_env(content: str) -> str | None:
    for line in content.splitlines():
        key, separator, value = line.partition("=")
        if key.strip() == "FILEZALL_AGENT_TOKEN" and separator:
            token = value.strip().strip("'\"")
            return token or None
    return None


def _replace_agent_state(site: SiteProfile, *, enabled: bool, token_ref: str | None) -> SiteProfile:
    from dataclasses import replace

    return replace(site, agent_enabled=enabled, agent_token_ref=token_ref)
