# FileZall M6 Agent Chunk Transfer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Agent HTTP chunk upload/download primitives, chunk status query, merge and verification calls, plus a queue-compatible Agent HTTP file client.

**Architecture:** Keep Agent chunk transfer code in `filezall_core` and build it on top of the existing `AgentHttpClient` request pattern. A new `AgentHttpFileClient` implements the `RemoteFileClient` boundary for transfer operations so `TransferRunner` can use Agent HTTP in the same path as SFTP/FTP. Directory listing over Agent HTTP is represented as a JSON file API for M6 tests.

**Tech Stack:** Python 3.12, pytest, dataclasses, stdlib `urllib`, `pathlib`, existing Agent client/resource models, existing `RemoteFileClient` and queue/runner code.

---

## Scope

This plan implements M6 from `docs/superpowers/specs/2026-06-24-filezall-design.md`:

- Chunk upload.
- Chunk download.
- Chunk status query.
- Merge and verification.
- Queue integration through `RemoteFileClient`.

This plan does not implement a real Linux Agent binary, SSH tunneling, background parallel chunk workers, or packaging.

## File Structure

- Create: `src/filezall_core/agent_transfer.py` - chunk request models and HTTP chunk API.
- Create: `src/filezall_core/agent_file_client.py` - `RemoteFileClient` adapter backed by Agent HTTP endpoints.
- Modify: `src/filezall_core/client_factory.py` - allow an injected Agent file-client factory for `Protocol.AGENT_HTTP`.
- Create: `tests/core/test_agent_transfer.py`.
- Create: `tests/core/test_agent_file_client.py`.
- Modify: `tests/core/test_client_factory.py`.
- Modify: `tests/core/test_transfer_runner.py`.

## Task 1: Agent Chunk Transfer API

**Files:**
- Create: `src/filezall_core/agent_transfer.py`
- Test: `tests/core/test_agent_transfer.py`

- [ ] **Step 1: Write failing chunk API tests**

Create tests with a fake opener and assert `AgentTransferClient` can upload a chunk, download a chunk, query status, merge chunks, and verify checksum. The fake opener records request URLs, methods, auth header, and request bodies.

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_agent_transfer.py -v
```

Expected: `ModuleNotFoundError: No module named 'filezall_core.agent_transfer'`.

- [ ] **Step 3: Implement chunk API**

Create `AgentTransferClient(base_url, token, opener=None, timeout=30)` with:

- `upload_chunk(remote_path, transfer_id, index, data) -> ChunkStatus`
- `download_chunk(remote_path, offset, size) -> bytes`
- `chunk_status(transfer_id) -> list[ChunkStatus]`
- `merge(transfer_id, remote_path, total_size) -> bool`
- `verify(remote_path, checksum) -> bool`

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_agent_transfer.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/agent_transfer.py tests/core/test_agent_transfer.py
git commit -m "feat: add Agent chunk transfer API"
```

## Task 2: Agent HTTP File Client

**Files:**
- Create: `src/filezall_core/agent_file_client.py`
- Test: `tests/core/test_agent_file_client.py`

- [ ] **Step 1: Write failing file-client tests**

Create tests with fake Agent API objects and assert:

- `list_directory(path)` maps JSON file entries to `RemoteFileEntry`.
- `upload_file_range(local_path, remote_path, offset)` uploads chunks starting at the offset and calls merge.
- `download_file_range(remote_path, local_path, offset)` appends downloaded bytes.
- `remote_size(path)` uses chunk status/metadata endpoint.
- `rename(source, destination)` delegates to Agent file API.

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_agent_file_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'filezall_core.agent_file_client'`.

- [ ] **Step 3: Implement Agent HTTP file client**

Create `AgentHttpFileClient(base_url, token, opener=None, chunk_size=1048576)` implementing `RemoteFileClient`. Reuse `AgentTransferClient` for chunk operations and implement file list/rename/size with JSON endpoints.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_agent_file_client.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/agent_file_client.py tests/core/test_agent_file_client.py
git commit -m "feat: add Agent HTTP file client"
```

## Task 3: Factory and Runner Integration

**Files:**
- Modify: `src/filezall_core/client_factory.py`
- Modify: `tests/core/test_client_factory.py`
- Modify: `tests/core/test_transfer_runner.py`

- [ ] **Step 1: Write failing integration tests**

Add tests that assert `create_remote_client(Protocol.AGENT_HTTP, agent_client_factory=...)` returns the injected Agent client. Add a `TransferRunner` test that uploads an `AGENT_HTTP` item through a fake Agent `RemoteFileClient`.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_client_factory.py tests/core/test_transfer_runner.py -v
```

Expected: failure because `create_remote_client` rejects Agent HTTP and does not accept `agent_client_factory`.

- [ ] **Step 3: Implement integration**

Modify `create_remote_client(protocol, agent_client_factory=None)`. If `Protocol.AGENT_HTTP` and no factory is provided, keep raising `RemoteConnectionError("Agent HTTP requires an Agent client factory")`; otherwise return `agent_client_factory()`.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_client_factory.py tests/core/test_transfer_runner.py -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/client_factory.py tests/core/test_client_factory.py tests/core/test_transfer_runner.py
git commit -m "feat: integrate Agent HTTP client factory"
```

## Task 4: Full M6 Verification

- [ ] **Step 1: Run all tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Expected: all non-live tests pass; optional live SFTP test is skipped unless configured.

- [ ] **Step 2: Run GUI smoke test**

Run:

```powershell
$env:FILEZALL_HOME = (Join-Path (Get-Location) '.filezall-smoke'); .\.venv\Scripts\python.exe -c "from PySide6.QtCore import QTimer; from PySide6.QtWidgets import QApplication; from filezall_desktop.app import create_main_window; app = QApplication([]); window = create_main_window(); window.show(); QTimer.singleShot(100, app.quit); raise SystemExit(app.exec())"
```

Expected: exit code 0.

- [ ] **Step 3: Check working tree**

Run:

```powershell
git status --short
```

Expected: no output.

## Self-Review

- Spec coverage: Chunk upload/download/status/merge/verification and queue-compatible Agent transfer are covered.
- Out of scope: Real Agent binary, SSH tunnel setup, background chunk workers, and installer packaging remain outside M6.
- Placeholder scan: No placeholders; tasks name concrete files and commands.
- Type consistency: Agent file client implements existing `RemoteFileClient`; factory keeps Agent configuration explicit.
