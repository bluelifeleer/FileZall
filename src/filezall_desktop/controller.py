from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path, PurePosixPath
from uuid import uuid4

from filezall_core.capabilities import resource_monitoring_message
from filezall_core.client_factory import create_remote_client
from filezall_core.local_files import list_local_directory
from filezall_core.models import AuthMode, ConflictPolicy, Direction, SiteProfile, TransferTask
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

    def disconnect(self) -> None:
        session = self._session
        try:
            if session is not None:
                closer = getattr(session, "disconnect", None) or getattr(session, "close", None)
                if closer is not None:
                    closer()
        finally:
            self._session = None
            self._connected_site = None
            self._connected_secret = None
        self._window.show_status("Disconnected")
        self._log("Disconnected")

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
        if self._queue_service is not None and self._connected_site is not None:
            self._queue_upload_file(local_path, remote_path)
            return
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

    def _queue_upload_file(self, local_path: Path, remote_path: PurePosixPath) -> None:
        site = self._require_connected_site()
        task = TransferTask(
            id=f"task-{uuid4()}",
            server_id=site.id,
            direction=Direction.UPLOAD,
            source_path=local_path.parent,
            destination_path=remote_path.parent,
            protocol=site.protocol,
            conflict_policy=ConflictPolicy.OVERWRITE,
        )
        item = task.create_item(
            item_id=f"item-{uuid4()}",
            relative_path=PurePosixPath(local_path.name),
            size_bytes=local_path.stat().st_size,
        )
        queue = self._require_queue()
        queue.add_task(task, [item])
        self._publish_transfer_items(site.id)
        self._window.show_status(f"Queued upload {local_path.name}")
        self._log(f"Queued upload {local_path} -> {remote_path}")
        session = self._require_session()
        client = getattr(session, "client", None)
        if client is None:
            queue.run_next(
                site.id,
                progress_callback=lambda _item: self._publish_transfer_items(site.id),
            )
        else:
            queue.run_next(
                site.id,
                client=client,
                progress_callback=lambda _item: self._publish_transfer_items(site.id),
            )
        self._publish_transfer_items(site.id)
        self._window.show_status(f"Uploaded {local_path.name}")
        self._log(f"Uploaded {local_path} to {remote_path}")

    def _publish_transfer_items(self, server_id: str | None = None) -> None:
        if not hasattr(self._window, "set_transfer_items"):
            return
        if self._queue_service is None:
            self._window.set_transfer_items([])
            return
        self._window.set_transfer_items(
            self._queue_service.list_items(server_id=server_id),
        )

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
            snapshot, status = self.load_resource_snapshot()
        except RuntimeError as exc:
            self._window.show_status(str(exc))
            return
        self._window.set_resource_snapshot(snapshot)
        self._window.show_status(status)

    def load_resource_snapshot(self):
        if self._resource_monitor_service is None and self._can_read_agent_resources():
            snapshot = self._agent_install_service.resource_snapshot(
                self._require_connected_site(),
                self._connected_secret,
            )
            return snapshot, "Agent resource snapshot refreshed"
        try:
            snapshot = self._require_resource_monitor().snapshot(self._require_connected_site())
        except ResourceMonitoringUnavailable as exc:
            raise RuntimeError(str(exc)) from exc
        return snapshot, "Resource snapshot refreshed"

    def show_process_detail(self, pid: int) -> None:
        if self._resource_monitor_service is None and self._can_read_agent_resources():
            detail = self._agent_install_service.process_detail(
                self._require_connected_site(),
                pid,
                self._connected_secret,
            )
            self._window.set_process_detail(detail)
            self._window.show_status(f"Loaded Agent process detail {pid}")
            return
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
        self.complete_agent_install(
            self.install_agent_with_progress(lambda message: self._log(message))
        )

    def install_agent_with_progress(self, progress_callback=None):
        if self._agent_install_service is None:
            raise RuntimeError("Agent installation is not configured.")
        return self._agent_install_service.install(
            self._require_connected_site(),
            self._connected_secret,
            progress_callback=progress_callback,
        )

    def complete_agent_install(self, result) -> None:
        if result.success and result.verified:
            self._mark_connected_site_agent_enabled(result)
            self._window.show_status("Agent installed and verified")
            self._log("Agent installed and verified")
        elif result.success:
            self._mark_connected_site_agent_enabled(result)
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
        self.complete_agent_uninstall(
            self.uninstall_agent_with_progress(lambda message: self._log(message))
        )

    def uninstall_agent_with_progress(self, progress_callback=None):
        if self._agent_install_service is None or not hasattr(
            self._agent_install_service,
            "uninstall",
        ):
            raise RuntimeError("Agent uninstallation is not configured.")
        return self._agent_install_service.uninstall(
            self._require_connected_site(),
            self._connected_secret,
            progress_callback=progress_callback,
        )

    def complete_agent_uninstall(self, result) -> None:
        if result.success:
            if self._connected_site is not None:
                self._connected_site = replace(
                    self._connected_site,
                    agent_enabled=False,
                    agent_token_ref=None,
                )
            self._window.show_status("Agent uninstalled")
            self._log("Agent uninstalled")
        else:
            self._window.show_status("Agent uninstallation failed")
            self._log("Agent uninstallation failed")

    def _mark_connected_site_agent_enabled(self, result) -> None:
        if self._connected_site is None:
            return
        self._connected_site = replace(
            self._connected_site,
            agent_enabled=True,
            agent_token_ref=getattr(result, "agent_token_ref", None)
            or self._connected_site.agent_token_ref,
        )

    def _require_session(self) -> RemoteSession:
        if self._session is None:
            raise RuntimeError("Remote session is not connected")
        return self._session

    def _can_read_agent_resources(self) -> bool:
        return (
            self._agent_install_service is not None
            and self._connected_site is not None
            and self._connected_site.agent_enabled
            and hasattr(self._agent_install_service, "resource_snapshot")
        )

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
