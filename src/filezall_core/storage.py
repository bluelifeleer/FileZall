from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_VERSION = 1


def initialize_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as connection:
        connection.execute("pragma foreign_keys = on")
        _create_schema(connection)
        _record_schema_version(connection)
        connection.commit()


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        create table if not exists schema_version (
            version integer not null,
            applied_at text not null default current_timestamp
        );

        create table if not exists site_profiles (
            id text primary key,
            name text not null,
            host text not null,
            port integer not null,
            protocol text not null,
            username text not null,
            auth_mode text not null,
            default_local_path text,
            default_remote_path text not null,
            credential_ref text,
            ssh_key_path text,
            agent_enabled integer not null default 0,
            agent_token_ref text,
            group_name text not null default '',
            created_at text not null default current_timestamp,
            updated_at text not null default current_timestamp
        );

        create table if not exists transfer_tasks (
            id text primary key,
            server_id text not null,
            direction text not null,
            source_path text not null,
            destination_path text not null,
            protocol text not null,
            conflict_policy text not null,
            status text not null,
            created_time text not null,
            created_at text not null default current_timestamp,
            updated_at text not null default current_timestamp
        );

        create table if not exists transfer_items (
            id text primary key,
            task_id text not null references transfer_tasks(id) on delete cascade,
            server_id text not null,
            direction text not null,
            source_path text not null,
            destination_path text not null,
            temporary_path text not null,
            size_bytes integer not null,
            modified_time text,
            checksum text,
            bytes_transferred integer not null default 0,
            status text not null,
            retry_count integer not null default 0,
            last_error text,
            started_at text,
            bytes_per_second real not null default 0,
            remaining_seconds real,
            failure_reason text,
            next_retry_at text,
            protocol text not null,
            created_at text not null default current_timestamp,
            updated_at text not null default current_timestamp
        );

        create table if not exists app_settings (
            key text primary key,
            value text not null,
            updated_at text not null default current_timestamp
        );
        """
    )
    _ensure_column(connection, "site_profiles", "group_name", "text not null default ''")
    _ensure_column(connection, "transfer_items", "started_at", "text")
    _ensure_column(connection, "transfer_items", "bytes_per_second", "real not null default 0")
    _ensure_column(connection, "transfer_items", "remaining_seconds", "real")
    _ensure_column(connection, "transfer_items", "failure_reason", "text")
    _ensure_column(connection, "transfer_items", "next_retry_at", "text")


def _record_schema_version(connection: sqlite3.Connection) -> None:
    current = connection.execute(
        "select version from schema_version order by applied_at desc limit 1"
    ).fetchone()
    if current is None or current[0] != SCHEMA_VERSION:
        connection.execute(
            "insert into schema_version(version) values (?)",
            (SCHEMA_VERSION,),
        )


def _ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    definition: str,
) -> None:
    columns = {
        str(row[1])
        for row in connection.execute(f"pragma table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(f"alter table {table_name} add column {column_name} {definition}")
