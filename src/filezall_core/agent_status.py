from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AgentStatus(StrEnum):
    UNKNOWN = "unknown"
    NOT_INSTALLED = "not_installed"
    INSTALLING = "installing"
    INSTALLED = "installed"
    OUTDATED = "outdated"
    UNHEALTHY = "unhealthy"
    UPDATE_AVAILABLE = "update_available"
    UNINSTALLING = "uninstalling"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class AgentStatusViewModel:
    state: AgentStatus
    version: str | None = None
    message: str = ""
    primary_action: str | None = None
    danger_action: str | None = None


def view_model_for_agent(
    installed: bool | None,
    *,
    version: str | None = None,
    message: str = "",
    current_version: str | None = None,
    healthy: bool = True,
    update_available: bool = False,
    operation: str | None = None,
    unavailable: bool = False,
) -> AgentStatusViewModel:
    if operation == "installing":
        return AgentStatusViewModel(
            state=AgentStatus.INSTALLING,
            version=version,
            message=message or "Agent install is running.",
            primary_action=None,
            danger_action=None,
        )
    if operation == "uninstalling":
        return AgentStatusViewModel(
            state=AgentStatus.UNINSTALLING,
            version=version,
            message=message or "Agent uninstall is running.",
            primary_action=None,
            danger_action=None,
        )
    if unavailable:
        return AgentStatusViewModel(
            state=AgentStatus.UNAVAILABLE,
            version=version,
            message=message or "Agent status is unavailable.",
            primary_action=None,
            danger_action=None,
        )
    if installed is None:
        return AgentStatusViewModel(
            state=AgentStatus.UNKNOWN,
            version=version,
            message=message or "Checking Agent status.",
            primary_action=None,
            danger_action=None,
        )
    if not installed:
        return AgentStatusViewModel(
            state=AgentStatus.NOT_INSTALLED,
            version=None,
            message=message or "Agent is not installed.",
            primary_action="Install Agent",
            danger_action=None,
        )
    if not healthy:
        return AgentStatusViewModel(
            state=AgentStatus.UNHEALTHY,
            version=version,
            message=message or "Agent is installed but unhealthy.",
            primary_action="Reinstall Agent",
            danger_action="Uninstall Agent",
        )
    if update_available or _is_older(version, current_version):
        return AgentStatusViewModel(
            state=AgentStatus.UPDATE_AVAILABLE if update_available else AgentStatus.OUTDATED,
            version=version,
            message=message or "Agent update is available.",
            primary_action="Update Agent",
            danger_action="Uninstall Agent",
        )
    return AgentStatusViewModel(
        state=AgentStatus.INSTALLED,
        version=version,
        message=message or "Agent is installed and healthy.",
        primary_action=None,
        danger_action="Uninstall Agent",
    )


def _is_older(current: str | None, target: str | None) -> bool:
    if not current or not target:
        return False
    try:
        current_parts = [int(part) for part in current.split(".")]
        target_parts = [int(part) for part in target.split(".")]
    except ValueError:
        return False
    width = max(len(current_parts), len(target_parts))
    current_parts += [0] * (width - len(current_parts))
    target_parts += [0] * (width - len(target_parts))
    return current_parts < target_parts
