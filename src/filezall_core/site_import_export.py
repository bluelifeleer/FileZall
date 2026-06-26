from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any

from filezall_core.models import AuthMode, Protocol, SiteProfile


def export_sites(sites: list[SiteProfile], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "sites": [_site_to_payload(site) for site in sites],
    }
    destination.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def import_sites(source: Path) -> list[SiteProfile]:
    payload = json.loads(source.read_text(encoding="utf-8"))
    return [_site_from_payload(site) for site in payload.get("sites", [])]


def _site_to_payload(site: SiteProfile) -> dict[str, Any]:
    return {
        "id": site.id,
        "name": site.name,
        "host": site.host,
        "port": site.port,
        "protocol": site.protocol.value,
        "username": site.username,
        "auth_mode": site.auth_mode.value,
        "default_local_path": str(site.default_local_path) if site.default_local_path else None,
        "default_remote_path": str(site.default_remote_path),
        "credential_ref": None,
        "ssh_key_path": str(site.ssh_key_path) if site.ssh_key_path else None,
        "agent_enabled": site.agent_enabled,
        "agent_token_ref": site.agent_token_ref,
        "group_name": site.group_name,
    }


def _site_from_payload(payload: dict[str, Any]) -> SiteProfile:
    local_path = payload.get("default_local_path")
    ssh_key_path = payload.get("ssh_key_path")
    return SiteProfile(
        id=str(payload["id"]),
        name=str(payload["name"]),
        host=str(payload["host"]),
        port=int(payload["port"]),
        protocol=Protocol(str(payload["protocol"])),
        username=str(payload["username"]),
        auth_mode=AuthMode(str(payload["auth_mode"])),
        default_local_path=Path(str(local_path)) if local_path else None,
        default_remote_path=PurePosixPath(str(payload.get("default_remote_path") or "~")),
        credential_ref=None,
        ssh_key_path=Path(str(ssh_key_path)) if ssh_key_path else None,
        agent_enabled=bool(payload.get("agent_enabled", False)),
        agent_token_ref=None,
        group_name=str(payload.get("group_name") or ""),
    )
