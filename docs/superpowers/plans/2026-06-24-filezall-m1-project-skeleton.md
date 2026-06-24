# FileZall M1 Project Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first runnable FileZall skeleton: Python package layout, test runner, core domain models, local SQLite storage, and a PySide6 desktop shell.

**Architecture:** This milestone creates the boundaries agreed in the design spec: `filezall_core` contains UI-independent business logic, while `filezall_desktop` contains PySide6 UI code. Storage is initialized through a small repository layer so later queue, site, and transfer features can reuse the same database.

**Tech Stack:** Python 3.11+, PySide6, pytest, SQLite, dataclasses, stdlib `pathlib`, `sqlite3`, and `enum`.

---

## Scope

The full design covers several independent subsystems. This plan implements only M1 from `docs/superpowers/specs/2026-06-24-filezall-design.md`:

- Project skeleton.
- Independent core package.
- Basic domain models.
- Local config/database setup.
- Basic PySide6 desktop shell.
- Test runner.

SFTP, FTP, FTPS, Agent, resource monitoring, transfer queues, resume logic, and packaging installers are handled by later milestone plans.

## File Structure

- Create: `pyproject.toml` - package metadata, dependencies, pytest config, console entry points.
- Create: `src/filezall_core/__init__.py` - core package version export.
- Create: `src/filezall_core/models.py` - site and transfer dataclasses plus enums.
- Create: `src/filezall_core/app_paths.py` - deterministic app data paths with `FILEZALL_HOME` override.
- Create: `src/filezall_core/storage.py` - SQLite schema initialization and schema version handling.
- Create: `src/filezall_desktop/__init__.py` - desktop package marker.
- Create: `src/filezall_desktop/app.py` - QApplication bootstrap.
- Create: `src/filezall_desktop/main_window.py` - minimal main window layout.
- Create: `tests/core/test_package.py` - verifies package import/version.
- Create: `tests/core/test_models.py` - verifies core model behavior.
- Create: `tests/core/test_app_paths.py` - verifies app path resolution.
- Create: `tests/core/test_storage.py` - verifies SQLite schema.
- Create: `tests/desktop/test_main_window.py` - verifies desktop shell construction.
- Create: `.gitignore` - excludes Python, build, local DB, and brainstorm artifacts.

## Task 0: Repository and Tooling Baseline

**Files:**
- Create: `.gitignore`

- [ ] **Step 1: Confirm repository state**

Run:

```powershell
git status --short
```

Expected if the repository is already valid:

```text
?? docs/
```

Expected in the current workspace:

```text
fatal: not a git repository (or any of the parent directories): .git
```

- [ ] **Step 2: Initialize Git when needed**

Run this only if Step 1 reports that the workspace is not a Git repository:

```powershell
git init
```

Expected:

```text
Initialized empty Git repository in C:/Users/HUAWEI/www/FileZall/.git/
```

- [ ] **Step 3: Create `.gitignore`**

Add:

```gitignore
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.venv/
venv/
build/
dist/
*.egg-info/
*.db
*.sqlite
*.sqlite3
.filezall/
.superpowers/
```

- [ ] **Step 4: Commit baseline docs and ignore rules**

Run:

```powershell
git add .gitignore docs/superpowers/specs/2026-06-24-filezall-design.md docs/superpowers/plans/2026-06-24-filezall-m1-project-skeleton.md
git commit -m "docs: add FileZall design and M1 plan"
```

Expected:

```text
[main ...] docs: add FileZall design and M1 plan
```

## Task 1: Python Package Skeleton

**Files:**
- Create: `pyproject.toml`
- Create: `src/filezall_core/__init__.py`
- Test: `tests/core/test_package.py`

- [ ] **Step 1: Write the failing package import test**

Create `tests/core/test_package.py`:

```python
from filezall_core import __version__


def test_core_package_exports_version() -> None:
    assert __version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/core/test_package.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'filezall_core'
```

- [ ] **Step 3: Add package metadata and core package**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "filezall"
version = "0.1.0"
description = "Cross-platform desktop file transfer client with queued resumable transfers and optional Linux Agent."
requires-python = ">=3.11"
dependencies = [
    "PySide6>=6.7",
    "keyring>=25.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-qt>=4.4",
]

[project.scripts]
filezall = "filezall_desktop.app:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = "-ra"
```

Create `src/filezall_core/__init__.py`:

```python
__version__ = "0.1.0"
```

- [ ] **Step 4: Install development dependencies**

Run:

```powershell
python -m pip install -e ".[dev]"
```

Expected:

```text
Successfully installed filezall-0.1.0
```

- [ ] **Step 5: Run test to verify it passes**

Run:

```powershell
python -m pytest tests/core/test_package.py -v
```

Expected:

```text
tests/core/test_package.py::test_core_package_exports_version PASSED
```

- [ ] **Step 6: Commit**

Run:

```powershell
git add pyproject.toml src/filezall_core/__init__.py tests/core/test_package.py
git commit -m "chore: add Python package skeleton"
```

Expected:

```text
[main ...] chore: add Python package skeleton
```

## Task 2: Core Domain Models

**Files:**
- Create: `src/filezall_core/models.py`
- Test: `tests/core/test_models.py`

- [ ] **Step 1: Write failing model tests**

Create `tests/core/test_models.py`:

```python
from pathlib import PurePosixPath, Path

from filezall_core.models import (
    AuthMode,
    ConflictPolicy,
    Direction,
    Protocol,
    SiteProfile,
    TransferItem,
    TransferStatus,
    TransferTask,
)


def test_site_profile_defaults_to_user_home_remote_path() -> None:
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )

    assert site.default_remote_path == PurePosixPath("~")
    assert site.agent_enabled is False


def test_directory_task_expands_relative_file_items() -> None:
    task = TransferTask(
        id="task-1",
        server_id="site-1",
        direction=Direction.UPLOAD,
        source_path=Path("D:/release"),
        destination_path=PurePosixPath("/var/www/release"),
        protocol=Protocol.SFTP,
        conflict_policy=ConflictPolicy.SKIP,
    )

    item = task.create_item(
        item_id="item-1",
        relative_path=PurePosixPath("assets/app.js"),
        size_bytes=1200,
    )

    assert item.source_path == Path("D:/release/assets/app.js")
    assert item.destination_path == PurePosixPath("/var/www/release/assets/app.js")
    assert item.status == TransferStatus.PENDING
    assert item.bytes_transferred == 0


def test_transfer_item_marks_completion_when_all_bytes_transferred() -> None:
    item = TransferItem(
        id="item-1",
        task_id="task-1",
        server_id="site-1",
        direction=Direction.DOWNLOAD,
        source_path=PurePosixPath("/data/archive.zip"),
        destination_path=Path("D:/Downloads/archive.zip"),
        temporary_path=Path("D:/Downloads/.filezall.archive.zip.part"),
        size_bytes=4096,
        protocol=Protocol.SFTP,
    )

    completed = item.with_progress(4096)

    assert completed.status == TransferStatus.COMPLETED
    assert completed.bytes_transferred == 4096
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/core/test_models.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'filezall_core.models'
```

- [ ] **Step 3: Implement domain models**

Create `src/filezall_core/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path, PurePosixPath


class Protocol(StrEnum):
    SFTP = "sftp"
    FTP = "ftp"
    FTPS = "ftps"
    AGENT_HTTP = "agent_http"


class AuthMode(StrEnum):
    PASSWORD = "password"
    SSH_KEY = "ssh_key"


class Direction(StrEnum):
    UPLOAD = "upload"
    DOWNLOAD = "download"


class ConflictPolicy(StrEnum):
    OVERWRITE = "overwrite"
    SKIP = "skip"
    RENAME = "rename"


class TransferStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    FAILED = "failed"
    COMPLETED = "completed"
    CANCELED = "canceled"


@dataclass(frozen=True)
class SiteProfile:
    id: str
    name: str
    host: str
    port: int
    protocol: Protocol
    username: str
    auth_mode: AuthMode
    default_remote_path: PurePosixPath = PurePosixPath("~")
    default_local_path: Path | None = None
    credential_ref: str | None = None
    ssh_key_path: Path | None = None
    agent_enabled: bool = False
    agent_token_ref: str | None = None


@dataclass(frozen=True)
class TransferItem:
    id: str
    task_id: str
    server_id: str
    direction: Direction
    source_path: Path | PurePosixPath
    destination_path: Path | PurePosixPath
    temporary_path: Path | PurePosixPath
    size_bytes: int
    protocol: Protocol
    bytes_transferred: int = 0
    status: TransferStatus = TransferStatus.PENDING
    retry_count: int = 0
    last_error: str | None = None

    def with_progress(self, bytes_transferred: int) -> "TransferItem":
        next_status = (
            TransferStatus.COMPLETED
            if bytes_transferred >= self.size_bytes
            else TransferStatus.RUNNING
        )
        return replace(
            self,
            bytes_transferred=min(bytes_transferred, self.size_bytes),
            status=next_status,
        )


@dataclass(frozen=True)
class TransferTask:
    id: str
    server_id: str
    direction: Direction
    source_path: Path | PurePosixPath
    destination_path: Path | PurePosixPath
    protocol: Protocol
    conflict_policy: ConflictPolicy
    status: TransferStatus = TransferStatus.PENDING

    def create_item(
        self,
        item_id: str,
        relative_path: PurePosixPath,
        size_bytes: int,
    ) -> TransferItem:
        source = self._join_path(self.source_path, relative_path)
        destination = self._join_path(self.destination_path, relative_path)
        temporary = self._temporary_path(destination)
        return TransferItem(
            id=item_id,
            task_id=self.id,
            server_id=self.server_id,
            direction=self.direction,
            source_path=source,
            destination_path=destination,
            temporary_path=temporary,
            size_bytes=size_bytes,
            protocol=self.protocol,
        )

    @staticmethod
    def _join_path(base: Path | PurePosixPath, relative: PurePosixPath) -> Path | PurePosixPath:
        if isinstance(base, Path):
            return base.joinpath(*relative.parts)
        return base.joinpath(relative)

    @staticmethod
    def _temporary_path(path: Path | PurePosixPath) -> Path | PurePosixPath:
        part_name = f".filezall.{path.name}.part"
        return path.with_name(part_name)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
python -m pytest tests/core/test_models.py -v
```

Expected:

```text
tests/core/test_models.py::test_site_profile_defaults_to_user_home_remote_path PASSED
tests/core/test_models.py::test_directory_task_expands_relative_file_items PASSED
tests/core/test_models.py::test_transfer_item_marks_completion_when_all_bytes_transferred PASSED
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/models.py tests/core/test_models.py
git commit -m "feat: add core transfer domain models"
```

Expected:

```text
[main ...] feat: add core transfer domain models
```

## Task 3: Application Paths

**Files:**
- Create: `src/filezall_core/app_paths.py`
- Test: `tests/core/test_app_paths.py`

- [ ] **Step 1: Write failing app path tests**

Create `tests/core/test_app_paths.py`:

```python
from pathlib import Path

from filezall_core.app_paths import AppPaths, resolve_app_paths


def test_resolve_app_paths_uses_filezall_home_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FILEZALL_HOME", str(tmp_path))

    paths = resolve_app_paths()

    assert paths == AppPaths(
        root=tmp_path,
        database=tmp_path / "filezall.sqlite3",
        logs=tmp_path / "logs",
        downloads=tmp_path / "downloads",
    )


def test_app_paths_can_create_directories(tmp_path: Path) -> None:
    paths = AppPaths(
        root=tmp_path,
        database=tmp_path / "filezall.sqlite3",
        logs=tmp_path / "logs",
        downloads=tmp_path / "downloads",
    )

    paths.ensure_directories()

    assert paths.root.is_dir()
    assert paths.logs.is_dir()
    assert paths.downloads.is_dir()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/core/test_app_paths.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'filezall_core.app_paths'
```

- [ ] **Step 3: Implement path resolution**

Create `src/filezall_core/app_paths.py`:

```python
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    root: Path
    database: Path
    logs: Path
    downloads: Path

    def ensure_directories(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.logs.mkdir(parents=True, exist_ok=True)
        self.downloads.mkdir(parents=True, exist_ok=True)


def resolve_app_paths() -> AppPaths:
    override = os.environ.get("FILEZALL_HOME")
    root = Path(override).expanduser() if override else _default_root()
    return AppPaths(
        root=root,
        database=root / "filezall.sqlite3",
        logs=root / "logs",
        downloads=root / "downloads",
    )


def _default_root() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "FileZall"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "FileZall"
    return Path.home() / ".local" / "share" / "filezall"
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
python -m pytest tests/core/test_app_paths.py -v
```

Expected:

```text
tests/core/test_app_paths.py::test_resolve_app_paths_uses_filezall_home_override PASSED
tests/core/test_app_paths.py::test_app_paths_can_create_directories PASSED
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/app_paths.py tests/core/test_app_paths.py
git commit -m "feat: add application path resolution"
```

Expected:

```text
[main ...] feat: add application path resolution
```

## Task 4: SQLite Storage Initialization

**Files:**
- Create: `src/filezall_core/storage.py`
- Test: `tests/core/test_storage.py`

- [ ] **Step 1: Write failing storage tests**

Create `tests/core/test_storage.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/core/test_storage.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'filezall_core.storage'
```

- [ ] **Step 3: Implement database initialization**

Create `src/filezall_core/storage.py`:

```python
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
            bytes_transferred integer not null default 0,
            status text not null,
            retry_count integer not null default 0,
            last_error text,
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


def _record_schema_version(connection: sqlite3.Connection) -> None:
    current = connection.execute(
        "select version from schema_version order by applied_at desc limit 1"
    ).fetchone()
    if current is None or current[0] != SCHEMA_VERSION:
        connection.execute(
            "insert into schema_version(version) values (?)",
            (SCHEMA_VERSION,),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
python -m pytest tests/core/test_storage.py -v
```

Expected:

```text
tests/core/test_storage.py::test_initialize_database_creates_expected_tables PASSED
tests/core/test_storage.py::test_initialize_database_records_schema_version PASSED
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/storage.py tests/core/test_storage.py
git commit -m "feat: initialize local SQLite storage"
```

Expected:

```text
[main ...] feat: initialize local SQLite storage
```

## Task 5: PySide6 Desktop Shell

**Files:**
- Create: `src/filezall_desktop/__init__.py`
- Create: `src/filezall_desktop/main_window.py`
- Create: `src/filezall_desktop/app.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write failing desktop shell test**

Create `tests/desktop/test_main_window.py`:

```python
from filezall_desktop.main_window import MainWindow


def test_main_window_has_filezall_title(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "FileZall"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/desktop/test_main_window.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'filezall_desktop'
```

- [ ] **Step 3: Implement minimal desktop shell**

Create `src/filezall_desktop/__init__.py`:

```python
"""FileZall desktop package."""
```

Create `src/filezall_desktop/main_window.py`:

```python
from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("FileZall")
        self.resize(1280, 800)
        self._build_toolbar()
        self._build_central_layout()
        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("Ready")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Connection")
        toolbar.setMovable(False)
        toolbar.addWidget(QLabel("Site"))
        toolbar.addSeparator()
        toolbar.addAction("Connect")
        toolbar.addAction("Disconnect")
        self.addToolBar(toolbar)

    def _build_central_layout(self) -> None:
        root = QWidget(self)
        root_layout = QVBoxLayout(root)

        file_splitter = QSplitter(root)
        file_splitter.addWidget(self._build_file_panel("Local Files"))
        file_splitter.addWidget(self._build_file_panel("Remote Files"))
        file_splitter.setSizes([640, 640])

        transfer_table = QTableWidget(0, 5, root)
        transfer_table.setHorizontalHeaderLabels(
            ["Server", "Direction", "File", "Progress", "Status"]
        )

        root_layout.addWidget(file_splitter, stretch=4)
        root_layout.addWidget(QLabel("Transfer Center"), stretch=0)
        root_layout.addWidget(transfer_table, stretch=1)
        self.setCentralWidget(root)

    def _build_file_panel(self, title: str) -> QWidget:
        panel = QWidget(self)
        layout = QVBoxLayout(panel)
        header = QHBoxLayout()
        header.addWidget(QLabel(title))
        header.addStretch()
        header.addWidget(QPushButton("Refresh"))

        table = QTableWidget(1, 4, panel)
        table.setHorizontalHeaderLabels(["Name", "Size", "Type", "Modified"])
        table.setItem(0, 0, QTableWidgetItem("No directory loaded"))
        table.setItem(0, 1, QTableWidgetItem(""))
        table.setItem(0, 2, QTableWidgetItem(""))
        table.setItem(0, 3, QTableWidgetItem(""))

        layout.addLayout(header)
        layout.addWidget(table)
        return panel
```

Create `src/filezall_desktop/app.py`:

```python
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from filezall_desktop.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run desktop test to verify it passes**

Run:

```powershell
python -m pytest tests/desktop/test_main_window.py -v
```

Expected:

```text
tests/desktop/test_main_window.py::test_main_window_has_filezall_title PASSED
```

- [ ] **Step 5: Launch the desktop shell manually**

Run:

```powershell
python -m filezall_desktop.app
```

Expected:

```text
The FileZall window opens with local and remote file panels and a Transfer Center table.
```

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/filezall_desktop tests/desktop/test_main_window.py
git commit -m "feat: add PySide6 desktop shell"
```

Expected:

```text
[main ...] feat: add PySide6 desktop shell
```

## Task 6: Full M1 Verification

**Files:**
- Verify all files created in Tasks 1-5.

- [ ] **Step 1: Run all tests**

Run:

```powershell
python -m pytest -v
```

Expected:

```text
tests/core/test_app_paths.py::test_resolve_app_paths_uses_filezall_home_override PASSED
tests/core/test_app_paths.py::test_app_paths_can_create_directories PASSED
tests/core/test_models.py::test_site_profile_defaults_to_user_home_remote_path PASSED
tests/core/test_models.py::test_directory_task_expands_relative_file_items PASSED
tests/core/test_models.py::test_transfer_item_marks_completion_when_all_bytes_transferred PASSED
tests/core/test_package.py::test_core_package_exports_version PASSED
tests/core/test_storage.py::test_initialize_database_creates_expected_tables PASSED
tests/core/test_storage.py::test_initialize_database_records_schema_version PASSED
tests/desktop/test_main_window.py::test_main_window_has_filezall_title PASSED
```

- [ ] **Step 2: Verify console entry point**

Run:

```powershell
filezall
```

Expected:

```text
The FileZall desktop window opens.
```

- [ ] **Step 3: Commit verification notes if any docs changed**

Run:

```powershell
git status --short
```

Expected:

```text
No output when the working tree is clean.
```

If documentation was updated during verification, run:

```powershell
git add docs
git commit -m "docs: update M1 verification notes"
```

Expected:

```text
[main ...] docs: update M1 verification notes
```

## Self-Review

- Spec coverage: This plan covers M1 only. M2-M7 remain separate milestone plans.
- Placeholder scan: This plan contains concrete file paths, code blocks, commands, and expected outputs.
- Type consistency: `Protocol`, `AuthMode`, `Direction`, `ConflictPolicy`, `TransferStatus`, `SiteProfile`, `TransferTask`, and `TransferItem` are introduced in Task 2 and used consistently by tests.
- Verification: Full M1 verification requires dependency installation and a working graphical environment for PySide6.
