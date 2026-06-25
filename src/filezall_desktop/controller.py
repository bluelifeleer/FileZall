from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path, PurePosixPath

from filezall_core.capabilities import resource_monitoring_message
from filezall_core.client_factory import create_remote_client
from filezall_core.local_files import list_local_directory
from filezall_core.models import AuthMode, SiteProfile
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
        self._session: RemoteSession | None = None
        self._connected_site: SiteProfile | None = None
        self._connected_secret: str | None = None

    def load_saved_sites(self) -> None:
        if self._site_repository is None:
            self._window.set_site_profiles([])
            return
        self._window.set_site_profiles(self._site_repository.list())

    def load_local_directory(self, path: Path) -> None:
        entries = self._local_lister(path)
        self._window.set_local_entries(entries)
        self._window.show_status(f"Loaded local directory {path}")

    def connect(self, site: SiteProfile, password: str | None = None) -> None:
        site = self._save_site_if_configured(site, password)
        password = password or self._secret_for_site(site)
        self._session = self._session_factory(site)
        self._connected_site = site
        self._connected_secret = password
        entries = self._session.connect_and_list_default(password=password)
        self._window.set_remote_entries(entries, self._session.current_remote_path)
        if hasattr(self._window, "set_monitoring_status"):
            self._window.set_monitoring_status(resource_monitoring_message(site.protocol))
        self._window.show_status(f"Connected to {site.name}")

    def list_remote_directory(self, path: PurePosixPath) -> None:
        entries = self._require_session().list_directory(path)
        self._window.set_remote_entries(entries, path)
        self._window.show_status(f"Loaded remote directory {path}")

    def upload_file(self, local_path: Path, remote_path: PurePosixPath) -> None:
        self._require_session().upload_file(local_path, remote_path)
        self._window.show_status(f"Uploaded {local_path.name}")

    def download_file(self, remote_path: PurePosixPath, local_path: Path) -> None:
        self._require_session().download_file(remote_path, local_path)
        self._window.show_status(f"Downloaded {remote_path.name}")

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
        elif result.success:
            self._window.show_status("Agent installed")
        else:
            self._window.show_status("Agent installation failed")

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
    ) -> SiteProfile:
        if self._site_repository is None:
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
