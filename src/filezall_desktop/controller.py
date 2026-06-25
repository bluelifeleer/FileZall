from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path, PurePosixPath

from filezall_core.capabilities import resource_monitoring_message
from filezall_core.client_factory import create_remote_client
from filezall_core.local_files import list_local_directory
from filezall_core.models import AuthMode, Direction, SiteProfile
from filezall_core.resource_monitor import ResourceMonitoringUnavailable
from filezall_core.session import RemoteSession


class MainWindowController:
    def __init__(
        self,
        window,
        local_lister: Callable[[Path], list] = list_local_directory,
        session_factory: Callable[[SiteProfile], RemoteSession] | None = None,
        site_repository=None,
        credential_service=None,
        queue_service=None,
        resource_monitor_service=None,
        agent_install_service=None,
        log_service=None,
    ) -> None:
        self._window = window
        self._local_lister = local_lister
        self._session_factory = session_factory or (
            lambda site: RemoteSession(site=site, client=create_remote_client(site.protocol))
        )
        self._site_repository = site_repository
        self._credential_service = credential_service
        self._queue_service = queue_service
        self._resource_monitor_service = resource_monitor_service
        self._agent_install_service = agent_install_service
        self._log_service = log_service
        self._session: RemoteSession | None = None
        self._connected_site: SiteProfile | None = None
        self._connected_secret: str | None = None

    def load_saved_sites(self) -> None:
        if self._site_repository is None:
            self._window.set_site_profiles([])
            return
        self._window.set_site_profiles(self._site_repository.list(), secret_lookup=self.secret_for_site)

    def secret_for_site(self, site: SiteProfile) -> str | None:
        return self._secret_for_site(site)

    def load_local_directory(self, path: Path) -> None:
        entries = self._local_lister(path)
        if hasattr(self._window, "set_local_directory_path"):
            self._window.set_local_directory_path(path)
        self._window.set_local_entries(entries)
        self._window.show_status(f"Loaded local directory {path}")
        self._log(f"Loaded local directory {path}")

    def connect(
        self,
        site: SiteProfile,
        password: str | None = None,
        remember_secret: bool = True,
    ) -> None:
        site = self._save_site_if_configured(site, password, remember_secret)
        password = password or self._secret_for_site(site)
        self._session = self._session_factory(site)
        self._connected_site = site
        self._connected_secret = password
        entries = self._session.connect_and_list_default(password=password)
        self._window.set_remote_entries(entries, self._session.current_remote_path)
        if hasattr(self._window, "set_monitoring_status"):
            self._window.set_monitoring_status(resource_monitoring_message(site.protocol))
        self._window.show_status(f"Connected to {site.name}")
        self._log(f"Connected to {site.name}")

    def list_remote_directory(self, path: PurePosixPath) -> None:
        entries = self._require_session().list_directory(path)
        self._window.set_remote_entries(entries, path)
        self._window.show_status(f"Loaded remote directory {path}")
        self._log(f"Loaded remote directory {path}")

    def heartbeat(self) -> bool:
        try:
            session = self._require_session()
            session.list_directory(session.current_remote_path)
        except Exception:
            return False
        return True

    def upload_file(self, local_path: Path, remote_path: PurePosixPath) -> None:
        self._require_session().upload_file(local_path, remote_path)
        self._window.show_status(f"Uploaded {local_path.name}")
        self._log(f"Uploaded {local_path} to {remote_path}")

    def download_file(self, remote_path: PurePosixPath, local_path: Path) -> None:
        self._require_session().download_file(remote_path, local_path)
        self._window.show_status(f"Downloaded {remote_path.name}")
        self._log(f"Downloaded {remote_path} to {local_path}")

    def delete_path(self, path: Path | PurePosixPath, remote: bool) -> None:
        location = "remote" if remote else "local"
        self._window.show_status(f"Delete requested for {location} path {path}")
        self._log(f"Delete requested for {location} path {path}")

    def add_to_queue(
        self,
        source_path: Path | PurePosixPath,
        destination_path: Path | PurePosixPath,
        direction: Direction,
    ) -> None:
        self._window.show_status(f"Queued {direction.value} {source_path}")
        self._log(f"Queued {direction.value} {source_path} -> {destination_path}")

    def create_directory(self, path: Path | PurePosixPath, remote: bool) -> None:
        location = "remote" if remote else "local"
        self._window.show_status(f"Create directory requested in {location} path {path}")
        self._log(f"Create directory requested in {location} path {path}")

    def create_file(self, path: Path | PurePosixPath, remote: bool) -> None:
        location = "remote" if remote else "local"
        self._window.show_status(f"Create file requested in {location} path {path}")
        self._log(f"Create file requested in {location} path {path}")

    def pause_transfer(self, task_id: str) -> None:
        self._require_queue().pause_task(task_id)
        self._window.show_status(f"Paused transfer task {task_id}")

    def resume_transfer(self, task_id: str) -> None:
        self._require_queue().resume_task(task_id)
        self._window.show_status(f"Resumed transfer task {task_id}")

    def cancel_transfer(self, task_id: str) -> None:
        self._require_queue().cancel_task(task_id)
        self._window.show_status(f"Canceled transfer task {task_id}")

    def retry_transfer(self, task_id: str) -> None:
        self._require_queue().retry_failed(task_id)
        self._window.show_status(f"Retried transfer task {task_id}")

    def refresh_resources(self) -> None:
        try:
            snapshot = self._require_resource_monitor().snapshot(self._require_connected_site())
        except ResourceMonitoringUnavailable as exc:
            self._window.show_status(str(exc))
            return
        self._window.set_resource_snapshot(snapshot)
        self._window.show_status("Resource snapshot refreshed")

    def show_process_detail(self, pid: int) -> None:
        detail = self._require_resource_monitor().process_detail(
            self._require_connected_site(),
            pid,
        )
        if detail is not None:
            self._window.set_process_detail(detail)
            self._window.show_status(f"Loaded process detail {pid}")

    def install_agent(self) -> None:
        if self._agent_install_service is None:
            self._window.show_status("Agent installation is not configured.")
            return
        result = self._agent_install_service.install(
            self._require_connected_site(),
            self._connected_secret,
        )
        if result.success and result.verified:
            self._window.show_status("Agent installed and verified")
            self._log("Agent installed and verified")
        elif result.success:
            self._window.show_status("Agent installed")
            self._log("Agent installed")
        else:
            self._window.show_status("Agent installation failed")
            self._log("Agent installation failed")

    def uninstall_agent(self) -> None:
        if self._agent_install_service is None or not hasattr(
            self._agent_install_service,
            "uninstall",
        ):
            self._window.show_status("Agent uninstallation is not configured.")
            return
        result = self._agent_install_service.uninstall(
            self._require_connected_site(),
            self._connected_secret,
        )
        if result.success:
            self._window.show_status("Agent uninstalled")
            self._log("Agent uninstalled")
        else:
            self._window.show_status("Agent uninstallation failed")
            self._log("Agent uninstallation failed")

    def _require_session(self) -> RemoteSession:
        if self._session is None:
            raise RuntimeError("Remote session is not connected")
        return self._session

    def _require_queue(self):
        if self._queue_service is None:
            raise RuntimeError("Transfer queue is not configured")
        return self._queue_service

    def _require_resource_monitor(self):
        if self._resource_monitor_service is None:
            raise RuntimeError("Resource monitor is not configured")
        return self._resource_monitor_service

    def _require_connected_site(self) -> SiteProfile:
        if self._connected_site is None:
            raise RuntimeError("Remote session is not connected")
        return self._connected_site

    def _save_site_if_configured(
        self,
        site: SiteProfile,
        password: str | None,
        remember_secret: bool,
    ) -> SiteProfile:
        if self._site_repository is None or not remember_secret:
            return site

        if password and self._credential_service is not None:
            purpose = "password" if site.auth_mode == AuthMode.PASSWORD else "ssh-passphrase"
            credential_ref = self._credential_service.save_secret(site.id, purpose, password)
            site = replace(site, credential_ref=credential_ref)

        self._site_repository.save(site)
        return site

    def _secret_for_site(self, site: SiteProfile) -> str | None:
        if self._credential_service is None:
            return None
        return self._credential_service.get_secret(site.credential_ref)

    def _log(self, message: str) -> None:
        if hasattr(self._window, "append_log"):
            self._window.append_log(message)
        elif self._log_service is not None:
            self._log_service.append(message)
