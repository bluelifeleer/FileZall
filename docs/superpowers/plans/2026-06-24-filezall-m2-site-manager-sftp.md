# FileZall M2 Site Manager and SFTP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first usable file-transfer workflow: save site profiles, connect to SFTP with password or SSH key metadata, browse local and remote directories, and upload/download one file at a time.

**Architecture:** Keep protocol and persistence logic in `filezall_core`; keep PySide6 widgets thin and event-driven in `filezall_desktop`. SFTP is introduced behind a protocol adapter interface so FTP, FTPS, Agent HTTP, queues, and resumable transfer can plug into the same boundary in later milestones.

**Tech Stack:** Python 3.12 in `.venv`, PySide6, pytest, pytest-qt, SQLite, keyring, Paramiko, dataclasses, pathlib, and dependency-injected adapter factories for tests.

---

## Scope

This plan implements M2 from `docs/superpowers/specs/2026-06-24-filezall-design.md`:

- Site profile persistence.
- Password and SSH key auth metadata.
- SFTP adapter boundary.
- Default remote home directory.
- Local and remote dual-pane browsing.
- Single-file upload and download through SFTP.

This plan does not implement global queues, resumable transfer, directory recursion, FTP/FTPS, Agent, resource monitoring, packaging installers, or multi-server concurrency. Those belong to M3-M7.

## File Structure

- Modify: `pyproject.toml` - add `paramiko`.
- Modify: `src/filezall_core/models.py` - add `RemoteFileEntry`, `LocalFileEntry`, and auth fields needed by SFTP connection.
- Modify: `src/filezall_core/storage.py` - add schema helpers for site persistence.
- Create: `src/filezall_core/site_repository.py` - CRUD for `SiteProfile`.
- Create: `src/filezall_core/credentials.py` - credential service wrapper over `keyring`.
- Create: `src/filezall_core/local_files.py` - local directory listing.
- Create: `src/filezall_core/protocols.py` - remote file client interface and exceptions.
- Create: `src/filezall_core/sftp_adapter.py` - Paramiko-backed SFTP implementation.
- Create: `src/filezall_core/session.py` - connect/list/upload/download orchestration.
- Modify: `src/filezall_desktop/main_window.py` - add connection bar, path bars, and local/remote tables.
- Create: `src/filezall_desktop/widgets.py` - reusable connection and file-panel widgets.
- Create: `tests/core/test_site_repository.py`.
- Create: `tests/core/test_credentials.py`.
- Create: `tests/core/test_local_files.py`.
- Create: `tests/core/test_sftp_adapter.py`.
- Create: `tests/core/test_session.py`.
- Modify: `tests/desktop/test_main_window.py`.
- Create: `tests/integration/test_sftp_live.py` - skipped unless SFTP env vars are set.

## Task 0: Dependency and Baseline

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Write the dependency expectation test**

Create `tests/core/test_dependencies.py`:

```python
import importlib.util


def test_paramiko_is_available_for_sftp_adapter() -> None:
    assert importlib.util.find_spec("paramiko") is not None
```

- [ ] **Step 2: Run test to verify it fails before dependency change**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_dependencies.py -v
```

Expected before adding the dependency:

```text
AssertionError: assert None is not None
```

If Paramiko is already installed transitively, continue and still add it explicitly to `pyproject.toml`.

- [ ] **Step 3: Add Paramiko dependency**

Modify `pyproject.toml`:

```toml
dependencies = [
    "PySide6>=6.7",
    "keyring>=25.0",
    "paramiko>=3.5",
]
```

- [ ] **Step 4: Install updated package**

Run:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Expected:

```text
Successfully installed filezall-0.1.0
```

- [ ] **Step 5: Run baseline tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Expected:

```text
All collected tests pass.
```

- [ ] **Step 6: Commit**

Run:

```powershell
git add pyproject.toml tests/core/test_dependencies.py
git commit -m "chore: add SFTP dependency"
```

Expected:

```text
[master ...] chore: add SFTP dependency
```

## Task 1: Site Profile Repository

**Files:**
- Modify: `src/filezall_core/storage.py`
- Create: `src/filezall_core/site_repository.py`
- Test: `tests/core/test_site_repository.py`

- [ ] **Step 1: Write failing repository tests**

Create `tests/core/test_site_repository.py`:

```python
from pathlib import Path, PurePosixPath

from filezall_core.models import AuthMode, Protocol, SiteProfile
from filezall_core.site_repository import SiteRepository
from filezall_core.storage import initialize_database


def test_site_repository_saves_and_loads_profile(tmp_path: Path) -> None:
    database = tmp_path / "filezall.sqlite3"
    initialize_database(database)
    repository = SiteRepository(database)
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
        default_remote_path=PurePosixPath("/home/deploy"),
        default_local_path=tmp_path,
        credential_ref="cred-site-1",
    )

    repository.save(site)

    assert repository.get("site-1") == site


def test_site_repository_lists_profiles_ordered_by_name(tmp_path: Path) -> None:
    database = tmp_path / "filezall.sqlite3"
    initialize_database(database)
    repository = SiteRepository(database)

    repository.save(
        SiteProfile(
            id="b",
            name="Beta",
            host="beta.example.com",
            port=22,
            protocol=Protocol.SFTP,
            username="deploy",
            auth_mode=AuthMode.SSH_KEY,
            ssh_key_path=Path("C:/keys/beta.pem"),
        )
    )
    repository.save(
        SiteProfile(
            id="a",
            name="Alpha",
            host="alpha.example.com",
            port=22,
            protocol=Protocol.SFTP,
            username="deploy",
            auth_mode=AuthMode.PASSWORD,
        )
    )

    assert [site.name for site in repository.list()] == ["Alpha", "Beta"]


def test_site_repository_deletes_profile(tmp_path: Path) -> None:
    database = tmp_path / "filezall.sqlite3"
    initialize_database(database)
    repository = SiteRepository(database)
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )
    repository.save(site)

    repository.delete("site-1")

    assert repository.get("site-1") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_site_repository.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'filezall_core.site_repository'
```

- [ ] **Step 3: Implement repository**

Create `src/filezall_core/site_repository.py`:

```python
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
                    ssh_key_path, agent_enabled, agent_token_ref, updated_at
                )
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
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
                       ssh_key_path, agent_enabled, agent_token_ref
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
                       ssh_key_path, agent_enabled, agent_token_ref
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
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_site_repository.py -v
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/site_repository.py tests/core/test_site_repository.py
git commit -m "feat: add site profile repository"
```

Expected:

```text
[master ...] feat: add site profile repository
```

## Task 2: Credential Service

**Files:**
- Create: `src/filezall_core/credentials.py`
- Test: `tests/core/test_credentials.py`

- [ ] **Step 1: Write failing credential tests**

Create `tests/core/test_credentials.py`:

```python
from filezall_core.credentials import CredentialService


class FakeKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}
        self.deleted: list[tuple[str, str]] = []

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        self.deleted.append((service, username))
        self.values.pop((service, username), None)


def test_credential_service_stores_password_by_reference() -> None:
    backend = FakeKeyring()
    service = CredentialService(backend=backend)

    ref = service.save_secret("site-1", "password", "s3cret")

    assert ref == "site-1:password"
    assert service.get_secret(ref) == "s3cret"


def test_credential_service_deletes_secret() -> None:
    backend = FakeKeyring()
    service = CredentialService(backend=backend)
    ref = service.save_secret("site-1", "agent-token", "token")

    service.delete_secret(ref)

    assert service.get_secret(ref) is None
    assert backend.deleted == [("FileZall", "site-1:agent-token")]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_credentials.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'filezall_core.credentials'
```

- [ ] **Step 3: Implement credential service**

Create `src/filezall_core/credentials.py`:

```python
from __future__ import annotations

import keyring


class CredentialService:
    def __init__(self, backend=keyring, service_name: str = "FileZall") -> None:
        self._backend = backend
        self._service_name = service_name

    def save_secret(self, site_id: str, purpose: str, secret: str) -> str:
        ref = f"{site_id}:{purpose}"
        self._backend.set_password(self._service_name, ref, secret)
        return ref

    def get_secret(self, ref: str | None) -> str | None:
        if not ref:
            return None
        return self._backend.get_password(self._service_name, ref)

    def delete_secret(self, ref: str | None) -> None:
        if not ref:
            return
        self._backend.delete_password(self._service_name, ref)
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_credentials.py -v
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/credentials.py tests/core/test_credentials.py
git commit -m "feat: add credential service"
```

Expected:

```text
[master ...] feat: add credential service
```

## Task 3: Local File Listing

**Files:**
- Modify: `src/filezall_core/models.py`
- Create: `src/filezall_core/local_files.py`
- Test: `tests/core/test_local_files.py`

- [ ] **Step 1: Write failing local file tests**

Create `tests/core/test_local_files.py`:

```python
from pathlib import Path

from filezall_core.local_files import list_local_directory


def test_list_local_directory_returns_sorted_entries(tmp_path: Path) -> None:
    (tmp_path / "zeta.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "alpha").mkdir()

    entries = list_local_directory(tmp_path)

    assert [entry.name for entry in entries] == ["alpha", "zeta.txt"]
    assert entries[0].is_dir is True
    assert entries[1].size_bytes == 5


def test_list_local_directory_rejects_files(tmp_path: Path) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text("hello", encoding="utf-8")

    try:
        list_local_directory(file_path)
    except NotADirectoryError as exc:
        assert str(file_path) in str(exc)
    else:
        raise AssertionError("expected NotADirectoryError")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_local_files.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'filezall_core.local_files'
```

- [ ] **Step 3: Add local file model and listing service**

Append to `src/filezall_core/models.py`:

```python
@dataclass(frozen=True)
class LocalFileEntry:
    path: Path
    name: str
    is_dir: bool
    size_bytes: int
    modified_time: datetime
```

Create `src/filezall_core/local_files.py`:

```python
from __future__ import annotations

from pathlib import Path

from filezall_core.models import LocalFileEntry


def list_local_directory(path: Path) -> list[LocalFileEntry]:
    if not path.is_dir():
        raise NotADirectoryError(str(path))
    entries: list[LocalFileEntry] = []
    for child in path.iterdir():
        stat = child.stat()
        entries.append(
            LocalFileEntry(
                path=child,
                name=child.name,
                is_dir=child.is_dir(),
                size_bytes=0 if child.is_dir() else stat.st_size,
                modified_time=_datetime_from_timestamp(stat.st_mtime),
            )
        )
    return sorted(entries, key=lambda entry: (not entry.is_dir, entry.name.lower()))


def _datetime_from_timestamp(value: float):
    from datetime import UTC, datetime

    return datetime.fromtimestamp(value, tz=UTC)
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_local_files.py -v
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/models.py src/filezall_core/local_files.py tests/core/test_local_files.py
git commit -m "feat: add local file listing"
```

Expected:

```text
[master ...] feat: add local file listing
```

## Task 4: Remote Protocol Interface and Fake Adapter

**Files:**
- Modify: `src/filezall_core/models.py`
- Create: `src/filezall_core/protocols.py`
- Test: `tests/core/test_protocols.py`

- [ ] **Step 1: Write failing protocol tests**

Create `tests/core/test_protocols.py`:

```python
from pathlib import Path, PurePosixPath

from filezall_core.models import RemoteFileEntry
from filezall_core.protocols import FakeRemoteClient


def test_fake_remote_client_lists_home_directory() -> None:
    client = FakeRemoteClient(
        entries={
            PurePosixPath("/home/deploy"): [
                RemoteFileEntry(
                    path=PurePosixPath("/home/deploy/app.log"),
                    name="app.log",
                    is_dir=False,
                    size_bytes=100,
                    modified_time=None,
                )
            ]
        },
        home=PurePosixPath("/home/deploy"),
    )

    assert client.home_directory() == PurePosixPath("/home/deploy")
    assert client.list_directory(PurePosixPath("/home/deploy"))[0].name == "app.log"


def test_fake_remote_client_records_upload_and_download(tmp_path: Path) -> None:
    client = FakeRemoteClient(entries={}, home=PurePosixPath("/home/deploy"))
    local_file = tmp_path / "app.zip"
    local_file.write_text("build", encoding="utf-8")
    download_file = tmp_path / "download.zip"

    client.upload_file(local_file, PurePosixPath("/home/deploy/app.zip"))
    client.download_file(PurePosixPath("/home/deploy/app.zip"), download_file)

    assert client.uploads == [(local_file, PurePosixPath("/home/deploy/app.zip"))]
    assert client.downloads == [(PurePosixPath("/home/deploy/app.zip"), download_file)]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_protocols.py -v
```

Expected:

```text
ImportError
```

- [ ] **Step 3: Add remote model and protocol interface**

Append to `src/filezall_core/models.py`:

```python
@dataclass(frozen=True)
class RemoteFileEntry:
    path: PurePosixPath
    name: str
    is_dir: bool
    size_bytes: int
    modified_time: datetime | None
```

Create `src/filezall_core/protocols.py`:

```python
from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Protocol as TypingProtocol

from filezall_core.models import RemoteFileEntry, SiteProfile


class RemoteConnectionError(RuntimeError):
    pass


class RemoteFileClient(TypingProtocol):
    def connect(self, site: SiteProfile, password: str | None = None) -> None:
        ...

    def close(self) -> None:
        ...

    def home_directory(self) -> PurePosixPath:
        ...

    def list_directory(self, path: PurePosixPath) -> list[RemoteFileEntry]:
        ...

    def upload_file(self, local_path: Path, remote_path: PurePosixPath) -> None:
        ...

    def download_file(self, remote_path: PurePosixPath, local_path: Path) -> None:
        ...


class FakeRemoteClient:
    def __init__(
        self,
        entries: dict[PurePosixPath, list[RemoteFileEntry]],
        home: PurePosixPath,
    ) -> None:
        self._entries = entries
        self._home = home
        self.connected_site: SiteProfile | None = None
        self.uploads: list[tuple[Path, PurePosixPath]] = []
        self.downloads: list[tuple[PurePosixPath, Path]] = []
        self.closed = False

    def connect(self, site: SiteProfile, password: str | None = None) -> None:
        self.connected_site = site

    def close(self) -> None:
        self.closed = True

    def home_directory(self) -> PurePosixPath:
        return self._home

    def list_directory(self, path: PurePosixPath) -> list[RemoteFileEntry]:
        return self._entries.get(path, [])

    def upload_file(self, local_path: Path, remote_path: PurePosixPath) -> None:
        self.uploads.append((local_path, remote_path))

    def download_file(self, remote_path: PurePosixPath, local_path: Path) -> None:
        self.downloads.append((remote_path, local_path))
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_protocols.py -v
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/models.py src/filezall_core/protocols.py tests/core/test_protocols.py
git commit -m "feat: add remote protocol interface"
```

Expected:

```text
[master ...] feat: add remote protocol interface
```

## Task 5: Paramiko SFTP Adapter

**Files:**
- Create: `src/filezall_core/sftp_adapter.py`
- Test: `tests/core/test_sftp_adapter.py`

- [ ] **Step 1: Write failing SFTP adapter tests**

Create `tests/core/test_sftp_adapter.py`:

```python
from pathlib import Path, PurePosixPath

from filezall_core.models import AuthMode, Protocol, SiteProfile
from filezall_core.sftp_adapter import SftpAdapter


class FakeSftpAttributes:
    def __init__(self, filename: str, st_mode: int, st_size: int, st_mtime: int) -> None:
        self.filename = filename
        self.st_mode = st_mode
        self.st_size = st_size
        self.st_mtime = st_mtime


class FakeSftpClient:
    def __init__(self) -> None:
        self.listdir_path = None
        self.put_calls = []
        self.get_calls = []

    def normalize(self, path: str) -> str:
        return "/home/deploy" if path == "." else path

    def listdir_attr(self, path: str):
        self.listdir_path = path
        return [FakeSftpAttributes("app.log", 0o100644, 42, 1_700_000_000)]

    def put(self, local_path: str, remote_path: str) -> None:
        self.put_calls.append((local_path, remote_path))

    def get(self, remote_path: str, local_path: str) -> None:
        self.get_calls.append((remote_path, local_path))

    def close(self) -> None:
        pass


class FakeSSHClient:
    def __init__(self) -> None:
        self.connect_kwargs = None
        self.sftp = FakeSftpClient()
        self.closed = False

    def set_missing_host_key_policy(self, policy) -> None:
        self.policy = policy

    def connect(self, **kwargs) -> None:
        self.connect_kwargs = kwargs

    def open_sftp(self) -> FakeSftpClient:
        return self.sftp

    def close(self) -> None:
        self.closed = True


class FakeParamiko:
    AutoAddPolicy = object

    def __init__(self) -> None:
        self.client = FakeSSHClient()

    def SSHClient(self) -> FakeSSHClient:
        return self.client


def test_sftp_adapter_connects_with_password() -> None:
    fake_paramiko = FakeParamiko()
    adapter = SftpAdapter(paramiko_module=fake_paramiko)
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )

    adapter.connect(site, password="secret")

    assert fake_paramiko.client.connect_kwargs["hostname"] == "example.com"
    assert fake_paramiko.client.connect_kwargs["username"] == "deploy"
    assert fake_paramiko.client.connect_kwargs["password"] == "secret"


def test_sftp_adapter_lists_uploads_and_downloads(tmp_path: Path) -> None:
    fake_paramiko = FakeParamiko()
    adapter = SftpAdapter(paramiko_module=fake_paramiko)
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )
    adapter.connect(site, password="secret")

    entries = adapter.list_directory(PurePosixPath("/home/deploy"))
    adapter.upload_file(tmp_path / "local.txt", PurePosixPath("/home/deploy/local.txt"))
    adapter.download_file(PurePosixPath("/home/deploy/app.log"), tmp_path / "app.log")

    assert entries[0].name == "app.log"
    assert entries[0].size_bytes == 42
    assert fake_paramiko.client.sftp.put_calls == [
        (str(tmp_path / "local.txt"), "/home/deploy/local.txt")
    ]
    assert fake_paramiko.client.sftp.get_calls == [
        ("/home/deploy/app.log", str(tmp_path / "app.log"))
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_sftp_adapter.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'filezall_core.sftp_adapter'
```

- [ ] **Step 3: Implement SFTP adapter**

Create `src/filezall_core/sftp_adapter.py`:

```python
from __future__ import annotations

import stat
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import paramiko

from filezall_core.models import AuthMode, RemoteFileEntry, SiteProfile
from filezall_core.protocols import RemoteConnectionError


class SftpAdapter:
    def __init__(self, paramiko_module=paramiko) -> None:
        self._paramiko = paramiko_module
        self._ssh = None
        self._sftp = None

    def connect(self, site: SiteProfile, password: str | None = None) -> None:
        client = self._paramiko.SSHClient()
        client.set_missing_host_key_policy(self._paramiko.AutoAddPolicy())
        kwargs = {
            "hostname": site.host,
            "port": site.port,
            "username": site.username,
            "timeout": 15,
        }
        if site.auth_mode == AuthMode.PASSWORD:
            kwargs["password"] = password
        elif site.ssh_key_path:
            kwargs["key_filename"] = str(site.ssh_key_path)
            if password:
                kwargs["passphrase"] = password
        try:
            client.connect(**kwargs)
            self._ssh = client
            self._sftp = client.open_sftp()
        except Exception as exc:
            raise RemoteConnectionError(str(exc)) from exc

    def close(self) -> None:
        if self._sftp:
            self._sftp.close()
        if self._ssh:
            self._ssh.close()

    def home_directory(self) -> PurePosixPath:
        return PurePosixPath(self._require_sftp().normalize("."))

    def list_directory(self, path: PurePosixPath) -> list[RemoteFileEntry]:
        entries: list[RemoteFileEntry] = []
        for attrs in self._require_sftp().listdir_attr(str(path)):
            child_path = path / attrs.filename
            entries.append(
                RemoteFileEntry(
                    path=child_path,
                    name=attrs.filename,
                    is_dir=stat.S_ISDIR(attrs.st_mode),
                    size_bytes=0 if stat.S_ISDIR(attrs.st_mode) else int(attrs.st_size),
                    modified_time=datetime.fromtimestamp(attrs.st_mtime, tz=UTC)
                    if attrs.st_mtime
                    else None,
                )
            )
        return sorted(entries, key=lambda entry: (not entry.is_dir, entry.name.lower()))

    def upload_file(self, local_path: Path, remote_path: PurePosixPath) -> None:
        self._require_sftp().put(str(local_path), str(remote_path))

    def download_file(self, remote_path: PurePosixPath, local_path: Path) -> None:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        self._require_sftp().get(str(remote_path), str(local_path))

    def _require_sftp(self):
        if self._sftp is None:
            raise RemoteConnectionError("SFTP client is not connected")
        return self._sftp
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_sftp_adapter.py -v
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/sftp_adapter.py tests/core/test_sftp_adapter.py
git commit -m "feat: add Paramiko SFTP adapter"
```

Expected:

```text
[master ...] feat: add Paramiko SFTP adapter
```

## Task 6: Core SFTP Session Orchestration

**Files:**
- Create: `src/filezall_core/session.py`
- Test: `tests/core/test_session.py`

- [ ] **Step 1: Write failing session tests**

Create `tests/core/test_session.py`:

```python
from pathlib import Path, PurePosixPath

from filezall_core.models import AuthMode, Protocol, RemoteFileEntry, SiteProfile
from filezall_core.protocols import FakeRemoteClient
from filezall_core.session import RemoteSession


def test_remote_session_connects_and_lists_default_home() -> None:
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )
    client = FakeRemoteClient(
        entries={
            PurePosixPath("/home/deploy"): [
                RemoteFileEntry(
                    path=PurePosixPath("/home/deploy/app.log"),
                    name="app.log",
                    is_dir=False,
                    size_bytes=100,
                    modified_time=None,
                )
            ]
        },
        home=PurePosixPath("/home/deploy"),
    )

    session = RemoteSession(site=site, client=client)
    entries = session.connect_and_list_home(password="secret")

    assert client.connected_site == site
    assert session.current_remote_path == PurePosixPath("/home/deploy")
    assert entries[0].name == "app.log"


def test_remote_session_uploads_and_downloads_one_file(tmp_path: Path) -> None:
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )
    client = FakeRemoteClient(entries={}, home=PurePosixPath("/home/deploy"))
    session = RemoteSession(site=site, client=client)
    session.connect_and_list_home(password="secret")
    local_file = tmp_path / "build.zip"
    local_file.write_text("zip", encoding="utf-8")
    download_file = tmp_path / "copy.zip"

    session.upload_file(local_file, PurePosixPath("/home/deploy/build.zip"))
    session.download_file(PurePosixPath("/home/deploy/build.zip"), download_file)

    assert client.uploads == [(local_file, PurePosixPath("/home/deploy/build.zip"))]
    assert client.downloads == [(PurePosixPath("/home/deploy/build.zip"), download_file)]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_session.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'filezall_core.session'
```

- [ ] **Step 3: Implement session**

Create `src/filezall_core/session.py`:

```python
from __future__ import annotations

from pathlib import Path, PurePosixPath

from filezall_core.models import RemoteFileEntry, SiteProfile
from filezall_core.protocols import RemoteFileClient


class RemoteSession:
    def __init__(self, site: SiteProfile, client: RemoteFileClient) -> None:
        self.site = site
        self.client = client
        self.current_remote_path: PurePosixPath | None = None

    def connect_and_list_home(self, password: str | None = None) -> list[RemoteFileEntry]:
        self.client.connect(self.site, password=password)
        self.current_remote_path = self.client.home_directory()
        return self.client.list_directory(self.current_remote_path)

    def list_directory(self, path: PurePosixPath) -> list[RemoteFileEntry]:
        self.current_remote_path = path
        return self.client.list_directory(path)

    def upload_file(self, local_path: Path, remote_path: PurePosixPath) -> None:
        self.client.upload_file(local_path, remote_path)

    def download_file(self, remote_path: PurePosixPath, local_path: Path) -> None:
        self.client.download_file(remote_path, local_path)

    def close(self) -> None:
        self.client.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_session.py -v
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/session.py tests/core/test_session.py
git commit -m "feat: add remote session orchestration"
```

Expected:

```text
[master ...] feat: add remote session orchestration
```

## Task 7: Desktop Site and File Panels

**Files:**
- Create: `src/filezall_desktop/widgets.py`
- Modify: `src/filezall_desktop/main_window.py`
- Modify: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write failing desktop widget tests**

Replace `tests/desktop/test_main_window.py` with:

```python
from filezall_desktop.main_window import MainWindow


def test_main_window_has_filezall_title(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "FileZall"


def test_main_window_exposes_connection_and_file_panels(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.connection_bar.host_edit.placeholderText() == "Host"
    assert window.connection_bar.port_edit.text() == "22"
    assert window.local_panel.title.text() == "Local Files"
    assert window.remote_panel.title.text() == "Remote Files"
    assert window.transfer_table.columnCount() == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/desktop/test_main_window.py -v
```

Expected:

```text
AttributeError: 'MainWindow' object has no attribute 'connection_bar'
```

- [ ] **Step 3: Implement reusable widgets and update main window**

Create `src/filezall_desktop/widgets.py`:

```python
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ConnectionBar(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        self.site_selector = QComboBox(self)
        self.site_selector.addItem("Quick Connect")
        self.host_edit = QLineEdit(self)
        self.host_edit.setPlaceholderText("Host")
        self.port_edit = QLineEdit("22", self)
        self.port_edit.setFixedWidth(64)
        self.username_edit = QLineEdit(self)
        self.username_edit.setPlaceholderText("Username")
        self.protocol_selector = QComboBox(self)
        self.protocol_selector.addItems(["SFTP"])
        self.connect_button = QPushButton("Connect", self)
        self.disconnect_button = QPushButton("Disconnect", self)

        layout.addWidget(QLabel("Site", self))
        layout.addWidget(self.site_selector)
        layout.addWidget(self.host_edit)
        layout.addWidget(self.port_edit)
        layout.addWidget(self.username_edit)
        layout.addWidget(self.protocol_selector)
        layout.addWidget(self.connect_button)
        layout.addWidget(self.disconnect_button)


class FilePanel(QWidget):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        self.title = QLabel(title, self)
        self.path_edit = QLineEdit(self)
        self.refresh_button = QPushButton("Refresh", self)
        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["Name", "Size", "Type", "Modified"])

        header.addWidget(self.title)
        header.addWidget(self.path_edit)
        header.addWidget(self.refresh_button)
        layout.addLayout(header)
        layout.addWidget(self.table)

    def set_placeholder_row(self, text: str) -> None:
        self.table.setRowCount(1)
        self.table.setItem(0, 0, QTableWidgetItem(text))
        self.table.setItem(0, 1, QTableWidgetItem(""))
        self.table.setItem(0, 2, QTableWidgetItem(""))
        self.table.setItem(0, 3, QTableWidgetItem(""))
```

Replace `src/filezall_desktop/main_window.py` with:

```python
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QMainWindow, QSplitter, QStatusBar, QTableWidget, QToolBar, QVBoxLayout, QWidget

from filezall_desktop.widgets import ConnectionBar, FilePanel


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
        self.connection_bar = ConnectionBar(self)
        toolbar.addWidget(self.connection_bar)
        self.addToolBar(toolbar)

    def _build_central_layout(self) -> None:
        root = QWidget(self)
        root_layout = QVBoxLayout(root)

        file_splitter = QSplitter(root)
        self.local_panel = FilePanel("Local Files", self)
        self.remote_panel = FilePanel("Remote Files", self)
        self.local_panel.set_placeholder_row("No directory loaded")
        self.remote_panel.set_placeholder_row("Not connected")
        file_splitter.addWidget(self.local_panel)
        file_splitter.addWidget(self.remote_panel)
        file_splitter.setSizes([640, 640])

        self.transfer_table = QTableWidget(0, 5, root)
        self.transfer_table.setHorizontalHeaderLabels(
            ["Server", "Direction", "File", "Progress", "Status"]
        )

        root_layout.addWidget(file_splitter, stretch=4)
        root_layout.addWidget(QLabel("Transfer Center"), stretch=0)
        root_layout.addWidget(self.transfer_table, stretch=1)
        self.setCentralWidget(root)
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/desktop/test_main_window.py -v
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_desktop/main_window.py src/filezall_desktop/widgets.py tests/desktop/test_main_window.py
git commit -m "feat: add desktop site and file panels"
```

Expected:

```text
[master ...] feat: add desktop site and file panels
```

## Task 8: Optional Live SFTP Integration Test

**Files:**
- Create: `tests/integration/test_sftp_live.py`

- [ ] **Step 1: Add skipped live test**

Create `tests/integration/test_sftp_live.py`:

```python
import os
from pathlib import PurePosixPath

import pytest

from filezall_core.models import AuthMode, Protocol, SiteProfile
from filezall_core.sftp_adapter import SftpAdapter


@pytest.mark.skipif(
    not os.environ.get("FILEZALL_SFTP_HOST"),
    reason="FILEZALL_SFTP_HOST is not set",
)
def test_live_sftp_lists_home_directory() -> None:
    site = SiteProfile(
        id="live",
        name="Live",
        host=os.environ["FILEZALL_SFTP_HOST"],
        port=int(os.environ.get("FILEZALL_SFTP_PORT", "22")),
        protocol=Protocol.SFTP,
        username=os.environ["FILEZALL_SFTP_USERNAME"],
        auth_mode=AuthMode.PASSWORD,
    )
    adapter = SftpAdapter()
    try:
        adapter.connect(site, password=os.environ.get("FILEZALL_SFTP_PASSWORD"))
        home = adapter.home_directory()
        entries = adapter.list_directory(home)
    finally:
        adapter.close()

    assert isinstance(home, PurePosixPath)
    assert isinstance(entries, list)
```

- [ ] **Step 2: Run integration test without env vars**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_sftp_live.py -v
```

Expected:

```text
1 skipped
```

- [ ] **Step 3: Commit**

Run:

```powershell
git add tests/integration/test_sftp_live.py
git commit -m "test: add optional live SFTP integration check"
```

Expected:

```text
[master ...] test: add optional live SFTP integration check
```

## Task 9: Full M2 Verification

**Files:**
- Verify all M2 files.

- [ ] **Step 1: Run all tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Expected:

```text
All non-live tests pass and the live SFTP test is skipped unless FILEZALL_SFTP_HOST is set.
```

- [ ] **Step 2: Run GUI smoke test**

Run:

```powershell
.\.venv\Scripts\python.exe -c "from PySide6.QtCore import QTimer; from PySide6.QtWidgets import QApplication; from filezall_desktop.main_window import MainWindow; app = QApplication([]); window = MainWindow(); window.show(); QTimer.singleShot(100, app.quit); raise SystemExit(app.exec())"
```

Expected:

```text
Exit code 0.
```

- [ ] **Step 3: Check working tree**

Run:

```powershell
git status --short
```

Expected:

```text
No output.
```

## Self-Review

- Spec coverage: M2 covers site manager persistence, password and SSH key metadata, SFTP connection, home directory listing, local/remote browsing primitives, and single-file transfer calls.
- Out of scope: queues, resumable transfer, FTP/FTPS, Agent, resource monitoring, multi-server concurrency, and installers remain for M3-M7.
- Placeholder scan: This plan contains concrete files, tests, implementation snippets, commands, and expected results.
- Type consistency: `SiteProfile`, `RemoteFileEntry`, `LocalFileEntry`, `RemoteFileClient`, `SftpAdapter`, and `RemoteSession` are introduced before use.
- Verification: M2 can be verified without a real SFTP server using fake adapters and skipped live tests; a real SFTP server can be tested by setting `FILEZALL_SFTP_HOST`, `FILEZALL_SFTP_USERNAME`, and `FILEZALL_SFTP_PASSWORD`.
