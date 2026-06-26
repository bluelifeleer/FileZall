from __future__ import annotations

import sqlite3
from pathlib import Path


class SettingsRepository:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def get(self, key: str, default: str | None = None) -> str | None:
        with sqlite3.connect(self._database_path) as connection:
            row = connection.execute(
                "select value from app_settings where key = ?",
                (key,),
            ).fetchone()
        return str(row[0]) if row else default

    def set(self, key: str, value: str) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """
                insert into app_settings (key, value, updated_at)
                values (?, ?, current_timestamp)
                on conflict(key) do update set
                    value = excluded.value,
                    updated_at = current_timestamp
                """,
                (key, value),
            )
            connection.commit()

    def get_bool(self, key: str, default: bool = False) -> bool:
        value = self.get(key)
        if value is None:
            return default
        return value == "true"

    def set_bool(self, key: str, value: bool) -> None:
        self.set(key, "true" if value else "false")
