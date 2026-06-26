from __future__ import annotations

import sqlite3
from pathlib import Path, PurePosixPath

from filezall_core.models import AuthMode, Protocol, SiteProfile


class SiteRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def save(self, site: SiteProfile) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """
                insert into site_profiles (
                    id, name, host, port, protocol, username, auth_mode,
                    default_local_path, default_remote_path, credential_ref,
                    ssh_key_path, agent_enabled, agent_token_ref, group_name, updated_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
                on conflict(id) do update set
                    name = excluded.name,
                    host = excluded.host,
                    port = excluded.port,
                    protocol = excluded.protocol,
                    username = excluded.username,
                    auth_mode = excluded.auth_mode,
                    default_local_path = excluded.default_local_path,
                    default_remote_path = excluded.default_remote_path,
                    credential_ref = excluded.credential_ref,
                    ssh_key_path = excluded.ssh_key_path,
                    agent_enabled = excluded.agent_enabled,
                    agent_token_ref = excluded.agent_token_ref,
                    group_name = excluded.group_name,
                    updated_at = current_timestamp
                """,
                self._to_row(site),
            )
            connection.commit()

    def get(self, site_id: str) -> SiteProfile | None:
        with sqlite3.connect(self._database_path) as connection:
            row = connection.execute(
                """
                select id, name, host, port, protocol, username, auth_mode,
                       default_local_path, default_remote_path, credential_ref,
                       ssh_key_path, agent_enabled, agent_token_ref, group_name
                from site_profiles
                where id = ?
                """,
                (site_id,),
            ).fetchone()
        return self._from_row(row) if row else None

    def list(self) -> list[SiteProfile]:
        with sqlite3.connect(self._database_path) as connection:
            rows = connection.execute(
                """
                select id, name, host, port, protocol, username, auth_mode,
                       default_local_path, default_remote_path, credential_ref,
                       ssh_key_path, agent_enabled, agent_token_ref, group_name
                from site_profiles
                order by lower(name)
                """
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def delete(self, site_id: str) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute("delete from site_profiles where id = ?", (site_id,))
            connection.commit()

    @staticmethod
    def _to_row(site: SiteProfile) -> tuple[object, ...]:
        return (
            site.id,
            site.name,
            site.host,
            site.port,
            site.protocol.value,
            site.username,
            site.auth_mode.value,
            str(site.default_local_path) if site.default_local_path else None,
            str(site.default_remote_path),
            site.credential_ref,
            str(site.ssh_key_path) if site.ssh_key_path else None,
            1 if site.agent_enabled else 0,
            site.agent_token_ref,
            site.group_name,
        )

    @staticmethod
    def _from_row(row: sqlite3.Row | tuple[object, ...]) -> SiteProfile:
        return SiteProfile(
            id=str(row[0]),
            name=str(row[1]),
            host=str(row[2]),
            port=int(row[3]),
            protocol=Protocol(str(row[4])),
            username=str(row[5]),
            auth_mode=AuthMode(str(row[6])),
            default_local_path=Path(str(row[7])) if row[7] else None,
            default_remote_path=PurePosixPath(str(row[8])),
            credential_ref=str(row[9]) if row[9] else None,
            ssh_key_path=Path(str(row[10])) if row[10] else None,
            agent_enabled=bool(row[11]),
            agent_token_ref=str(row[12]) if row[12] else None,
            group_name=str(row[13]) if row[13] else "",
        )
