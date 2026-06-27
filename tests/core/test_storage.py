import sqlite3
from pathlib import Path

from filezall_core.storage import initialize_database


def test_initialize_database_creates_expected_tables(tmp_path: Path) -> None:
    database = tmp_path / "filezall.sqlite3"

    initialize_database(database)

    with sqlite3.connect(database) as connection:
        table_names = {
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type = 'table'"
            )
        }

    assert {
        "schema_version",
        "site_profiles",
        "transfer_tasks",
        "transfer_items",
        "app_settings",
    }.issubset(table_names)


def test_initialize_database_records_schema_version(tmp_path: Path) -> None:
    database = tmp_path / "filezall.sqlite3"

    initialize_database(database)

    with sqlite3.connect(database) as connection:
        version = connection.execute(
            "select version from schema_version order by applied_at desc limit 1"
        ).fetchone()[0]

    assert version == 1


def test_transfer_tables_include_metadata_columns(tmp_path: Path) -> None:
    database = tmp_path / "filezall.sqlite3"

    initialize_database(database)

    with sqlite3.connect(database) as connection:
        task_columns = {
            row[1] for row in connection.execute("pragma table_info(transfer_tasks)")
        }
        item_columns = {
            row[1] for row in connection.execute("pragma table_info(transfer_items)")
        }

    assert "created_time" in task_columns
    assert "modified_time" in item_columns
    assert "checksum" in item_columns
    assert "next_retry_at" in item_columns
