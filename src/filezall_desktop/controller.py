from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path, PurePosixPath
from uuid import uuid4

from filezall_core.agent_deployment import classify_agent_error
from filezall_core.agent_status import view_model_for_agent
from filezall_core.capabilities import resource_monitoring_message
from filezall_core import __version__
from filezall_core.client_factory import create_remote_client
from filezall_core.directory_plan import plan_local_directory
from filezall_core.local_files import list_local_directory
from filezall_core.models import AuthMode, ConflictPolicy, Direction, Protocol, SiteProfile, TransferTask
from filezall_core.resource_monitor import ResourceMonitoringUnavailable
from filezall_core.session import RemoteSession


def classify_connection_error(error: str) -> str:
    lowered = error.lower()
    if any(token in lowered for token in ["authentication failed", "auth failed", "bad authentication"]):
        return "Authentication failed. Check the username, password, SSH key, or passphrase."
    if any(
        token in lowered
        for token in [
            "connection refused",
            "timed out",
            "timeout",
            "unable to connect",
            "no route to host",
            "network is unreachable",
        ]
    ):
        return "Could not reach the server or port. Check the host, port, firewall, and network."
    if "agent token is not available" in lowered or "agent is not installed" in lowered:
        return "FileZall Agent is not installed or its token is missing. Install or update the Agent."
    if (
        "systemd" in lowered
        or "systemctl" in lowered
        or "health check failed" in lowered
        or "health endpoint" in lowered
    ):
        return classify_agent_error(error)
    if "permission denied" in lowered:
        return "Permission denied. Check the account permissions for the selected remote path."
    return error


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
        self._remote_directory_cache: dict[tuple[str, str], list] = {}

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
        result = self.connect_for_window(site, password, remember_secret)
        self._publish_connect_result(result)

    def connect_for_window(
        self,
        site: SiteProfile,
        password: str | None = None,
        remember_secret: bool = True,
    ) -> dict:
        logs: list[str] = []
        site = self._save_site_if_configured(site, password, remember_secret)
        password = password or self._secret_for_site(site)
        self._session = self._session_factory(site)
        self._connected_site = site
        self._connected_secret = password
        self._remote_directory_cache.clear()
        entries = self._session.connect_and_list_default(password=password)
        self._cache_remote_directory(self._session.current_remote_path, entries)
        result = {
            "entries": entries,
            "remote_path": self._session.current_remote_path,
            "monitoring_status": resource_monitoring_message(site.protocol),
            "agent_status": None,
            "agent_status_sequence": [],
            "agent_status_message": None,
            "agent_version": None,
            "resource_snapshot": None,
            "resource_status": None,
            "status": f"Connected to {site.name}",
            "logs": logs,
        }
        self._detect_agent_installation_for_result(site, password, result, logs)
        logs.append(f"Connected to {site.name}")
        return result

    def _publish_connect_result(self, result: dict) -> None:
        self._window.set_remote_entries(result["entries"], result["remote_path"])
        if hasattr(self._window, "set_monitoring_status"):
            self._window.set_monitoring_status(result["monitoring_status"])
        agent_status = result.get("agent_status")
        if hasattr(self._window, "set_agent_status"):
            for status in result.get("agent_status_sequence", []):
                self._window.set_agent_status(status)
                self._publish_agent_status_model(
                    status,
                    version=result.get("agent_version") if status is True else None,
                    message=result.get("agent_status_message") or "",
                )
            if agent_status is not None and not result.get("agent_status_sequence"):
                self._window.set_agent_status(agent_status)
                self._publish_agent_status_model(
                    agent_status,
                    version=result.get("agent_version") if agent_status is True else None,
                    message=result.get("agent_status_message") or "",
                )
        if result.get("agent_version") and hasattr(self._window, "set_agent_version"):
            self._window.set_agent_version(result["agent_version"])
        for message in result.get("logs", []):
            self._log(message)
        snapshot = result.get("resource_snapshot")
        if snapshot is not None:
            self._window.set_resource_snapshot(snapshot)
        self._window.show_status(result["status"])

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
            self._remote_directory_cache.clear()
        self._window.show_status("Disconnected")
        self._log("Disconnected")

    def list_remote_directory(self, path: PurePosixPath, *, force_refresh: bool = False) -> None:
        entries, path, status = self.load_remote_directory(path, force_refresh=force_refresh)
        self._window.set_remote_entries(entries, path)
        self._window.show_status(status)
        self._log(status)

    def load_remote_directory(self, path: PurePosixPath, *, force_refresh: bool = False):
        path = PurePosixPath(path)
        if not force_refresh:
            cached_entries = self._cached_remote_directory(path)
            if cached_entries is not None:
                return cached_entries, path, f"Loaded remote directory {path}"
        entries = self._require_session().list_directory(path)
        self._cache_remote_directory(path, entries)
        return entries, path, f"Loaded remote directory {path}"

    def heartbeat(self) -> bool:
        try:
            session = self._require_session()
            session.list_directory(session.current_remote_path)
        except Exception:
            return False
        return True

    def upload_file(
        self,
        local_path: Path,
        remote_path: PurePosixPath,
        conflict_policy: ConflictPolicy = ConflictPolicy.OVERWRITE,
    ) -> None:
        if self._queue_service is not None and self._connected_site is not None:
            if local_path.is_dir():
                self._queue_upload_directory(
                    local_path,
                    remote_path,
                    conflict_policy=conflict_policy,
                )
                return
            self._queue_upload_file(local_path, remote_path, conflict_policy=conflict_policy)
            return
        self._require_session().upload_file(local_path, remote_path)
        self._invalidate_remote_directory_cache_for(remote_path.parent)
        self._window.show_status(f"Uploaded {local_path.name}")
        self._log(f"Uploaded {local_path} to {remote_path}")

    def download_file(
        self,
        remote_path: PurePosixPath,
        local_path: Path,
        conflict_policy: ConflictPolicy = ConflictPolicy.OVERWRITE,
    ) -> None:
        if self._queue_service is not None and self._connected_site is not None:
            self._queue_download_file(
                remote_path,
                local_path,
                conflict_policy=conflict_policy,
            )
            return
        self._require_session().download_file(remote_path, local_path)
        self._invalidate_remote_directory_cache_for(remote_path.parent)
        self._window.show_status(f"Downloaded {remote_path.name}")
        self._log(f"Downloaded {remote_path} to {local_path}")

    def delete_path(
        self,
        path: Path | PurePosixPath,
        remote: bool,
        is_dir: bool | None = None,
    ) -> None:
        if remote:
            remote_path = PurePosixPath(path)
            self._require_session().delete_path(remote_path, is_dir=bool(is_dir))
            self._invalidate_remote_directory_cache_for(remote_path.parent, remote_path)
            message = f"Deleted remote path {remote_path}"
        else:
            local_path = Path(path)
            if is_dir is True or (is_dir is None and local_path.is_dir()):
                local_path.rmdir()
            else:
                local_path.unlink()
            message = f"Deleted local path {local_path}"
        self._window.show_status(message)
        self._log(message)

    def add_to_queue(
        self,
        source_path: Path | PurePosixPath,
        destination_path: Path | PurePosixPath,
        direction: Direction,
    ) -> None:
        self._window.show_status(f"Queued {direction.value} {source_path}")
        self._log(f"Queued {direction.value} {source_path} -> {destination_path}")

    def _queue_upload_directory(
        self,
        local_path: Path,
        remote_path: PurePosixPath,
        conflict_policy: ConflictPolicy,
    ) -> None:
        site = self._require_connected_site()
        plan = plan_local_directory(local_path, remote_path, direction=Direction.UPLOAD)
        task = TransferTask(
            id=f"task-{uuid4()}",
            server_id=site.id,
            direction=Direction.UPLOAD,
            source_path=local_path,
            destination_path=remote_path,
            protocol=site.protocol,
            conflict_policy=conflict_policy,
        )
        items = [
            task.create_item(
                item_id=f"item-{uuid4()}",
                relative_path=item.relative_path,
                size_bytes=item.size_bytes,
            )
            for item in plan.items
        ]
        self._require_queue().add_task(task, items)
        self._invalidate_remote_directory_cache_for(remote_path.parent, remote_path)
        self._publish_transfer_items(site.id)
        message = (
            f"Queued directory upload {local_path.name}: "
            f"{plan.total_files} files, {plan.total_bytes} bytes"
        )
        self._window.show_status(message)
        self._log(message)

    def _queue_upload_file(
        self,
        local_path: Path,
        remote_path: PurePosixPath,
        conflict_policy: ConflictPolicy,
    ) -> None:
        site = self._require_connected_site()
        task = TransferTask(
            id=f"task-{uuid4()}",
            server_id=site.id,
            direction=Direction.UPLOAD,
            source_path=local_path.parent,
            destination_path=remote_path.parent,
            protocol=site.protocol,
            conflict_policy=conflict_policy,
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
        self._invalidate_remote_directory_cache_for(remote_path.parent)
        self._publish_transfer_items(site.id)
        self._window.show_status(f"Uploaded {local_path.name}")
        self._log(f"Uploaded {local_path} to {remote_path}")

    def _queue_download_file(
        self,
        remote_path: PurePosixPath,
        local_path: Path,
        conflict_policy: ConflictPolicy,
    ) -> None:
        site = self._require_connected_site()
        task = TransferTask(
            id=f"task-{uuid4()}",
            server_id=site.id,
            direction=Direction.DOWNLOAD,
            source_path=remote_path.parent,
            destination_path=local_path.parent,
            protocol=site.protocol,
            conflict_policy=conflict_policy,
        )
        session = self._require_session()
        client = getattr(session, "client", None)
        remote_size = 0
        if client is not None and hasattr(client, "remote_size"):
            remote_size = client.remote_size(remote_path) or 0
        item = task.create_item(
            item_id=f"item-{uuid4()}",
            relative_path=PurePosixPath(remote_path.name),
            size_bytes=remote_size,
        )
        queue = self._require_queue()
        queue.add_task(task, [item])
        self._publish_transfer_items(site.id)
        self._window.show_status(f"Queued download {remote_path.name}")
        self._log(f"Queued download {remote_path} -> {local_path}")
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
        self._window.show_status(f"Downloaded {remote_path.name}")
        self._log(f"Downloaded {remote_path} to {local_path}")

    def _publish_transfer_items(self, server_id: str | None = None) -> None:
        if not hasattr(self._window, "set_transfer_items"):
            return
        if self._queue_service is None:
            self._window.set_transfer_items([])
            return
        self._window.set_transfer_items(
            self._queue_service.list_items(server_id=server_id),
        )

    def set_transfer_settings(self, settings) -> None:
        if self._queue_service is not None and hasattr(self._queue_service, "settings"):
            self._queue_service.settings = settings

    def create_directory(self, path: Path | PurePosixPath, remote: bool) -> None:
        if remote:
            target = PurePosixPath(path) / "New Folder"
            self._require_session().make_directory(target)
            self._invalidate_remote_directory_cache_for(PurePosixPath(path), target)
            message = f"Created remote directory {target}"
        else:
            target = _unique_local_child_path(Path(path), "New Folder", "")
            target.mkdir()
            message = f"Created local directory {target}"
        self._window.show_status(message)
        self._log(message)

    def create_file(self, path: Path | PurePosixPath, remote: bool) -> None:
        if remote:
            target = PurePosixPath(path) / "New File.txt"
            self._require_session().create_file(target)
            self._invalidate_remote_directory_cache_for(PurePosixPath(path))
            message = f"Created remote file {target}"
        else:
            target = _unique_local_child_path(Path(path), "New File", ".txt")
            target.touch()
            message = f"Created local file {target}"
        self._window.show_status(message)
        self._log(message)

    def rename_path(
        self,
        source_path: Path | PurePosixPath,
        destination_path: Path | PurePosixPath,
        remote: bool,
    ) -> None:
        if remote:
            remote_source = PurePosixPath(source_path)
            remote_destination = PurePosixPath(destination_path)
            self._require_session().rename(
                remote_source,
                remote_destination,
            )
            self._invalidate_remote_directory_cache_for(
                remote_source.parent,
                remote_source,
                remote_destination.parent,
                remote_destination,
            )
            message = f"Renamed remote path {source_path} to {destination_path}"
        else:
            Path(source_path).rename(Path(destination_path))
            message = f"Renamed local path {source_path} to {destination_path}"
        self._window.show_status(message)
        self._log(message)

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
                runner=self._connected_agent_runner(),
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
                runner=self._connected_agent_runner(),
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

    def stop_process(self, pid: int) -> None:
        self._signal_process(pid, "TERM", f"Stop signal sent to process {pid}")

    def restart_process(self, pid: int) -> None:
        self._signal_process(pid, "HUP", f"Restart signal sent to process {pid}")

    def _signal_process(self, pid: int, signal: str, status: str) -> None:
        if self._agent_install_service is None or not hasattr(
            self._agent_install_service,
            "signal_process",
        ):
            raise RuntimeError("Process actions require an installed FileZall Agent.")
        self._agent_install_service.signal_process(
            self._require_connected_site(),
            pid,
            signal,
            self._connected_secret,
            runner=self._connected_agent_runner(),
        )
        self._window.show_status(status)
        self._log(status)

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

    def _detect_agent_installation(self, site: SiteProfile, password: str | None) -> None:
        result = {
            "agent_status": None,
            "agent_status_sequence": [],
            "agent_status_message": None,
            "agent_version": None,
            "resource_snapshot": None,
            "resource_status": None,
        }
        logs: list[str] = []
        self._detect_agent_installation_for_result(site, password, result, logs)
        for message in logs:
            self._log(message)
        if hasattr(self._window, "set_agent_status"):
            for status in result.get("agent_status_sequence", []):
                self._window.set_agent_status(status)
            if result["agent_status"] is not None and not result.get("agent_status_sequence"):
                self._window.set_agent_status(result["agent_status"])
                self._publish_agent_status_model(result["agent_status"])
        if result.get("agent_version") and hasattr(self._window, "set_agent_version"):
            self._window.set_agent_version(result["agent_version"])
        if result["resource_snapshot"] is not None:
            self._window.set_resource_snapshot(result["resource_snapshot"])
        if result["agent_status_message"]:
            self._window.show_status(result["agent_status_message"])

    def _detect_agent_installation_for_result(
        self,
        site: SiteProfile,
        password: str | None,
        result: dict,
        logs: list[str],
    ) -> None:
        if site.protocol is Protocol.AGENT_HTTP:
            result["agent_status"] = True
            logs.append("Agent service installed")
            return
        if site.protocol is not Protocol.SFTP:
            return
        if self._agent_install_service is None or not hasattr(
            self._agent_install_service,
            "is_agent_installed",
        ):
            return
        result["agent_status_sequence"].append(None)
        self._publish_agent_status_model(None)
        logs.append("Agent detection started")
        try:
            agent_token_ref = None
            if hasattr(self._agent_install_service, "detect_agent_installation"):
                detection = self._agent_install_service.detect_agent_installation(
                    site,
                    password,
                    progress_callback=logs.append,
                )
                installed = detection.installed
                agent_token_ref = detection.agent_token_ref
                result["agent_version"] = getattr(detection, "agent_version", None)
            else:
                installed = self._agent_install_service.is_agent_installed(
                    site,
                    password,
                    progress_callback=logs.append,
                )
        except Exception as exc:
            logs.append(f"Agent detection failed: {classify_agent_error(str(exc))}")
            result["agent_status"] = False
            result["agent_status_sequence"].append(False)
            self._publish_agent_status_model(False, message=classify_agent_error(str(exc)))
            return
        if installed and agent_token_ref is not None:
            self._mark_connected_site_agent_enabled_ref(agent_token_ref)
            try:
                snapshot, status = self.load_resource_snapshot()
            except RuntimeError as exc:
                logs.append(f"Resource refresh failed: {exc}")
            else:
                result["resource_snapshot"] = snapshot
                result["resource_status"] = status
                logs.append(status)
        result["agent_status"] = installed
        result["agent_status_sequence"].append(installed)
        self._publish_agent_status_model(
            installed,
            version=result.get("agent_version"),
            message=result.get("agent_status_message") or "",
        )
        if installed and agent_token_ref is None:
            logs.append("Agent service installed but Agent token is not available")
            result["agent_status_message"] = (
                "Agent installed, but install/update is required to enable monitoring"
            )
        else:
            logs.append("Agent service installed" if installed else "Agent service not installed")

    def _publish_agent_status_model(
        self,
        installed: bool | None,
        *,
        version: str | None = None,
        message: str = "",
        healthy: bool = True,
        operation: str | None = None,
        unavailable: bool = False,
    ) -> None:
        if not hasattr(self._window, "set_agent_status_model"):
            return
        model = view_model_for_agent(
            installed,
            version=version,
            message=message,
            current_version=__version__,
            healthy=healthy,
            operation=operation,
            unavailable=unavailable,
        )
        self._window.set_agent_status_model(model)

    def _mark_connected_site_agent_enabled_ref(self, agent_token_ref: str) -> None:
        if self._connected_site is None:
            return
        self._connected_site = replace(
            self._connected_site,
            agent_enabled=True,
            agent_token_ref=agent_token_ref,
        )

    def _cache_remote_directory(self, path: PurePosixPath, entries: list) -> None:
        self._remote_directory_cache[self._remote_directory_cache_key(path)] = list(entries)

    def _cached_remote_directory(self, path: PurePosixPath) -> list | None:
        entries = self._remote_directory_cache.get(self._remote_directory_cache_key(path))
        if entries is None:
            return None
        return list(entries)

    def _invalidate_remote_directory_cache_for(self, *paths: PurePosixPath) -> None:
        if not self._remote_directory_cache:
            return
        site_key = self._remote_directory_cache_site_key()
        if not paths:
            self._remote_directory_cache = {
                key: entries
                for key, entries in self._remote_directory_cache.items()
                if key[0] != site_key
            }
            return
        prefixes = {str(PurePosixPath(path)) for path in paths}
        for key in list(self._remote_directory_cache):
            key_site, cached_path = key
            if key_site != site_key:
                continue
            if any(_remote_cache_path_matches(cached_path, prefix) for prefix in prefixes):
                del self._remote_directory_cache[key]

    def _remote_directory_cache_key(self, path: PurePosixPath) -> tuple[str, str]:
        return self._remote_directory_cache_site_key(), str(PurePosixPath(path))

    def _remote_directory_cache_site_key(self) -> str:
        if self._connected_site is not None:
            return self._connected_site.id
        return f"session:{id(self._require_session())}"

    def _require_session(self) -> RemoteSession:
        if self._session is None:
            raise RuntimeError("Remote session is not connected")
        return self._session

    def _connected_agent_runner(self):
        if self._session is None:
            return None
        client = getattr(self._session, "client", None)
        if client is not None and hasattr(client, "capture"):
            return client
        return None

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
        try:
            return self._credential_service.get_secret(site.credential_ref)
        except Exception as exc:
            raise RuntimeError(
                "Could not read the saved password from macOS Keychain. "
                "Enter the server password manually in the password field and connect again."
            ) from exc

    def _log(self, message: str) -> None:
        if hasattr(self._window, "append_log"):
            self._window.append_log(message)
        elif self._log_service is not None:
            self._log_service.append(message)


def _unique_local_child_path(parent: Path, stem: str, suffix: str) -> Path:
    candidate = parent / f"{stem}{suffix}"
    if not candidate.exists():
        return candidate
    index = 2
    while True:
        candidate = parent / f"{stem} ({index}){suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def _remote_cache_path_matches(cached_path: str, prefix: str) -> bool:
    if prefix == "/":
        return cached_path.startswith("/")
    normalized = prefix.rstrip("/")
    return cached_path == normalized or cached_path.startswith(f"{normalized}/")
