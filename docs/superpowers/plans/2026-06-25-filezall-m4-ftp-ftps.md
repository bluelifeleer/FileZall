# FileZall M4 FTP and FTPS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add FTP and FTPS browsing/transfer support behind the existing remote-client boundary, expose protocol selection in the desktop UI, and show clear resource-monitoring degradation messages for non-SSH protocols.

**Architecture:** Keep protocol-specific code in `filezall_core` adapters and route through a small protocol factory. Desktop code should only collect the selected protocol, create `SiteProfile` values, and display capability messages. FTP/FTPS use Python stdlib `ftplib`; SFTP stays on the existing Paramiko adapter.

**Tech Stack:** Python 3.12, pytest, PySide6, stdlib `ftplib`, existing dataclasses, existing `RemoteFileClient` protocol, SQLite site persistence.

---

## Scope

This plan implements M4 from `docs/superpowers/specs/2026-06-24-filezall-design.md`:

- FTP browsing and single-file transfer.
- FTPS browsing and single-file transfer.
- Protocol selection and routing from desktop connect flow.
- Protocol capability indicators for resource monitoring.
- Monitoring degradation messages for FTP/FTPS.

This plan does not implement Agent deployment, process metrics, chunked Agent HTTP transfer, package installers, or true multi-server UI tabs.

## File Structure

- Create: `src/filezall_core/ftp_adapter.py` - FTP and FTPS implementation of `RemoteFileClient`.
- Create: `src/filezall_core/client_factory.py` - maps `Protocol` to the correct remote client.
- Create: `src/filezall_core/capabilities.py` - describes resource-monitoring support per protocol.
- Modify: `src/filezall_desktop/controller.py` - default session factory uses protocol factory and reports monitoring capability after connect.
- Modify: `src/filezall_desktop/widgets.py` - protocol selector exposes SFTP, FTP, and FTPS.
- Modify: `src/filezall_desktop/main_window.py` - reads selected protocol and displays monitoring status.
- Modify: `tests/core/test_session.py` - verifies session works with FTP protocol clients through the factory boundary where needed.
- Create: `tests/core/test_ftp_adapter.py`.
- Create: `tests/core/test_client_factory.py`.
- Create: `tests/core/test_capabilities.py`.
- Modify: `tests/desktop/test_controller.py`.
- Modify: `tests/desktop/test_main_window.py`.

## Task 1: Protocol Capabilities

**Files:**
- Create: `src/filezall_core/capabilities.py`
- Test: `tests/core/test_capabilities.py`

- [ ] **Step 1: Write failing capability tests**

Create `tests/core/test_capabilities.py`:

```python
from filezall_core.capabilities import resource_monitoring_message
from filezall_core.models import Protocol


def test_resource_monitoring_message_for_sftp() -> None:
    assert resource_monitoring_message(Protocol.SFTP) == "Basic monitoring available through SSH."


def test_resource_monitoring_message_for_ftp_and_ftps() -> None:
    assert resource_monitoring_message(Protocol.FTP) == "Resource monitoring requires SSH or FileZall Agent."
    assert resource_monitoring_message(Protocol.FTPS) == "Resource monitoring requires SSH or FileZall Agent."
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_capabilities.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'filezall_core.capabilities'
```

- [ ] **Step 3: Implement capability helper**

Create `src/filezall_core/capabilities.py`:

```python
from __future__ import annotations

from filezall_core.models import Protocol


def resource_monitoring_message(protocol: Protocol) -> str:
    if protocol is Protocol.SFTP:
        return "Basic monitoring available through SSH."
    if protocol in {Protocol.FTP, Protocol.FTPS}:
        return "Resource monitoring requires SSH or FileZall Agent."
    if protocol is Protocol.AGENT_HTTP:
        return "Full monitoring available through FileZall Agent."
    return "Resource monitoring capability is unknown."
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_capabilities.py -v
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/capabilities.py tests/core/test_capabilities.py
git commit -m "feat: add protocol capability messages"
```

## Task 2: FTP and FTPS Adapter

**Files:**
- Create: `src/filezall_core/ftp_adapter.py`
- Test: `tests/core/test_ftp_adapter.py`

- [ ] **Step 1: Write failing adapter tests**

Create `tests/core/test_ftp_adapter.py` with fake FTP classes that capture calls:

```python
from pathlib import Path, PurePosixPath

from filezall_core.ftp_adapter import FtpAdapter
from filezall_core.models import AuthMode, Protocol, SiteProfile


class FakeFtp:
    def __init__(self) -> None:
        self.connected = None
        self.login_call = None
        self.cwd_path = "/home/deploy"
        self.prot_p_called = False
        self.stores = []
        self.retrieves = []
        self.renames = []
        self.closed = False
        self.size_map = {"/home/deploy/.filezall.app.zip.part": 3}
        self.entries = [
            ("app.log", {"type": "file", "size": "42", "modify": "20260625120000"}),
            ("public", {"type": "dir", "size": "0"}),
        ]

    def connect(self, host: str, port: int, timeout: int) -> None:
        self.connected = (host, port, timeout)

    def login(self, user: str, passwd: str | None) -> None:
        self.login_call = (user, passwd)

    def pwd(self) -> str:
        return self.cwd_path

    def mlsd(self, path: str):
        self.mlsd_path = path
        return self.entries

    def storbinary(self, command: str, fileobj, blocksize=8192, callback=None, rest=None) -> None:
        self.stores.append((command, fileobj.read(), rest))

    def retrbinary(self, command: str, callback, blocksize=8192, rest=None) -> None:
        self.retrieves.append((command, rest))
        callback(b"xyz")

    def size(self, path: str) -> int:
        if path not in self.size_map:
            raise FileNotFoundError(path)
        return self.size_map[path]

    def rename(self, source: str, destination: str) -> None:
        self.renames.append((source, destination))

    def quit(self) -> None:
        self.closed = True

    def prot_p(self) -> None:
        self.prot_p_called = True


class FakeFtps(FakeFtp):
    pass


class FakeFtpModule:
    def __init__(self) -> None:
        self.ftp = FakeFtp()
        self.ftps = FakeFtps()

    def FTP(self):
        return self.ftp

    def FTP_TLS(self):
        return self.ftps


def _site(protocol: Protocol) -> SiteProfile:
    return SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=21,
        protocol=protocol,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )


def test_ftp_adapter_connects_lists_and_transfers(tmp_path: Path) -> None:
    module = FakeFtpModule()
    adapter = FtpAdapter(protocol=Protocol.FTP, ftp_module=module)
    local_file = tmp_path / "app.zip"
    local_file.write_bytes(b"abcdef")

    adapter.connect(_site(Protocol.FTP), password="secret")
    entries = adapter.list_directory(PurePosixPath("/home/deploy"))
    adapter.upload_file(local_file, PurePosixPath("/home/deploy/app.zip"))
    adapter.download_file(PurePosixPath("/home/deploy/app.zip"), tmp_path / "copy.zip")

    assert module.ftp.connected == ("example.com", 21, 15)
    assert module.ftp.login_call == ("deploy", "secret")
    assert [entry.name for entry in entries] == ["public", "app.log"]
    assert module.ftp.stores[0][0] == "STOR /home/deploy/app.zip"
    assert module.ftp.retrieves == [("RETR /home/deploy/app.zip", None)]
    assert (tmp_path / "copy.zip").read_bytes() == b"xyz"


def test_ftps_adapter_enables_protected_data_channel() -> None:
    module = FakeFtpModule()
    adapter = FtpAdapter(protocol=Protocol.FTPS, ftp_module=module)

    adapter.connect(_site(Protocol.FTPS), password="secret")

    assert module.ftps.prot_p_called is True


def test_ftp_adapter_supports_resume_operations(tmp_path: Path) -> None:
    module = FakeFtpModule()
    adapter = FtpAdapter(protocol=Protocol.FTP, ftp_module=module)
    adapter.connect(_site(Protocol.FTP), password="secret")
    local_file = tmp_path / "app.zip"
    local_file.write_bytes(b"abcdef")

    assert adapter.remote_size(PurePosixPath("/home/deploy/.filezall.app.zip.part")) == 3
    assert adapter.remote_size(PurePosixPath("/home/deploy/missing.part")) is None

    adapter.upload_file_range(local_file, PurePosixPath("/home/deploy/.filezall.app.zip.part"), offset=3)
    adapter.download_file_range(PurePosixPath("/home/deploy/app.zip"), tmp_path / ".part", offset=2)
    adapter.rename(PurePosixPath("/home/deploy/.filezall.app.zip.part"), PurePosixPath("/home/deploy/app.zip"))

    assert module.ftp.stores[-1] == ("STOR /home/deploy/.filezall.app.zip.part", b"def", 3)
    assert module.ftp.retrieves[-1] == ("RETR /home/deploy/app.zip", 2)
    assert (tmp_path / ".part").read_bytes() == b"xyz"
    assert module.ftp.renames == [("/home/deploy/.filezall.app.zip.part", "/home/deploy/app.zip")]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_ftp_adapter.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'filezall_core.ftp_adapter'
```

- [ ] **Step 3: Implement FTP adapter**

Create `src/filezall_core/ftp_adapter.py` with `FtpAdapter(protocol, ftp_module=ftplib)`. Use `FTP` for `Protocol.FTP` and `FTP_TLS` plus `prot_p()` for `Protocol.FTPS`. Implement `connect`, `close`, `home_directory`, `list_directory` with `mlsd`, `upload_file`, `download_file`, `remote_size`, `upload_file_range`, `download_file_range`, and `rename`.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_ftp_adapter.py -v
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/ftp_adapter.py tests/core/test_ftp_adapter.py
git commit -m "feat: add FTP and FTPS adapter"
```

## Task 3: Protocol Client Factory

**Files:**
- Create: `src/filezall_core/client_factory.py`
- Test: `tests/core/test_client_factory.py`
- Modify: `src/filezall_desktop/controller.py`

- [ ] **Step 1: Write failing factory tests**

Create `tests/core/test_client_factory.py`:

```python
import pytest

from filezall_core.client_factory import create_remote_client
from filezall_core.ftp_adapter import FtpAdapter
from filezall_core.models import Protocol
from filezall_core.protocols import RemoteConnectionError
from filezall_core.sftp_adapter import SftpAdapter


def test_client_factory_creates_protocol_adapters() -> None:
    assert isinstance(create_remote_client(Protocol.SFTP), SftpAdapter)
    assert isinstance(create_remote_client(Protocol.FTP), FtpAdapter)
    assert isinstance(create_remote_client(Protocol.FTPS), FtpAdapter)


def test_client_factory_rejects_agent_http_until_m6() -> None:
    with pytest.raises(RemoteConnectionError, match="Agent HTTP is not available until M6"):
        create_remote_client(Protocol.AGENT_HTTP)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_client_factory.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'filezall_core.client_factory'
```

- [ ] **Step 3: Implement factory and controller default routing**

Create `src/filezall_core/client_factory.py`:

```python
from __future__ import annotations

from filezall_core.ftp_adapter import FtpAdapter
from filezall_core.models import Protocol
from filezall_core.protocols import RemoteConnectionError, RemoteFileClient
from filezall_core.sftp_adapter import SftpAdapter


def create_remote_client(protocol: Protocol) -> RemoteFileClient:
    if protocol is Protocol.SFTP:
        return SftpAdapter()
    if protocol in {Protocol.FTP, Protocol.FTPS}:
        return FtpAdapter(protocol=protocol)
    raise RemoteConnectionError("Agent HTTP is not available until M6")
```

Modify `src/filezall_desktop/controller.py` default session factory to use `create_remote_client(site.protocol)` instead of always creating `SftpAdapter`.

- [ ] **Step 4: Run factory and controller tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_client_factory.py tests/desktop/test_controller.py -v
```

Expected:

```text
All selected tests pass.
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/client_factory.py src/filezall_desktop/controller.py tests/core/test_client_factory.py
git commit -m "feat: route remote clients by protocol"
```

## Task 4: Desktop Protocol Selection and Monitoring Message

**Files:**
- Modify: `src/filezall_desktop/widgets.py`
- Modify: `src/filezall_desktop/main_window.py`
- Modify: `src/filezall_desktop/controller.py`
- Test: `tests/desktop/test_main_window.py`
- Test: `tests/desktop/test_controller.py`

- [ ] **Step 1: Write failing desktop tests**

Add tests that assert:

```python
assert [window.connection_bar.protocol_selector.itemText(i) for i in range(window.connection_bar.protocol_selector.count())] == ["SFTP", "FTP", "FTPS"]
```

Add a test that selects `FTP`, clicks connect, and asserts `site.protocol == Protocol.FTP`. Add a controller test that calls `connect()` with an FTP site and asserts the window receives `"Resource monitoring requires SSH or FileZall Agent."` through `set_monitoring_status`.

- [ ] **Step 2: Run desktop tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/desktop/test_main_window.py tests/desktop/test_controller.py -v
```

Expected:

```text
At least one assertion failure for missing FTP/FTPS selector items or missing set_monitoring_status call.
```

- [ ] **Step 3: Implement UI and controller capability wiring**

Modify `ConnectionBar` protocol selector to add `["SFTP", "FTP", "FTPS"]`. Modify `MainWindow._site_from_fields()` to map selected text to `Protocol.SFTP`, `Protocol.FTP`, or `Protocol.FTPS`. Add `monitoring_status_label` under the transfer center and a `set_monitoring_status(message)` method. Modify `MainWindowController.connect()` to call `self._window.set_monitoring_status(resource_monitoring_message(site.protocol))` when the method exists.

- [ ] **Step 4: Run desktop tests to verify they pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/desktop/test_main_window.py tests/desktop/test_controller.py -v
```

Expected:

```text
All selected tests pass.
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_desktop/widgets.py src/filezall_desktop/main_window.py src/filezall_desktop/controller.py tests/desktop/test_main_window.py tests/desktop/test_controller.py
git commit -m "feat: expose FTP protocols in desktop UI"
```

## Task 5: Full M4 Verification

**Files:**
- Verify all M4 files.

- [ ] **Step 1: Run all tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Expected:

```text
All non-live tests pass; optional live SFTP test is skipped unless configured.
```

- [ ] **Step 2: Run GUI smoke test**

Run:

```powershell
$env:FILEZALL_HOME = (Join-Path (Get-Location) '.filezall-smoke'); .\.venv\Scripts\python.exe -c "from PySide6.QtCore import QTimer; from PySide6.QtWidgets import QApplication; from filezall_desktop.app import create_main_window; app = QApplication([]); window = create_main_window(); window.show(); QTimer.singleShot(100, app.quit); raise SystemExit(app.exec())"
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

- Spec coverage: FTP/FTPS browsing and transfer are implemented through `FtpAdapter`; protocol selection and capability messages are covered in desktop tests.
- Out of scope: Agent install, resource metrics collection, process details, chunked transfer, packaging, and multi-server tabs remain for later milestones.
- Placeholder scan: No placeholders; every task names concrete files, commands, and expected outcomes.
- Type consistency: `Protocol.FTP` and `Protocol.FTPS` already exist in `models.py`; new factory returns existing `RemoteFileClient` implementations.
- Verification: M4 can be verified without a real FTP server through fake ftplib classes.
