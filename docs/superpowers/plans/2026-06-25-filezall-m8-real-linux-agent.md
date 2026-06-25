# FileZall M8 Real Linux Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a real stdlib Python Linux Agent service that implements the health, resource, process, file, chunk transfer, merge, verify, and rename endpoints already expected by the desktop client.

**Architecture:** The Agent lives under `agent/filezall_agent` and avoids third-party runtime dependencies. The HTTP layer is a thin `http.server` adapter over focused service modules for files, transfers, and resources. Tests run the Agent against a temporary root directory so file operations are safe and deterministic.

**Tech Stack:** Python 3.12, pytest, stdlib `http.server`, `urllib`, `json`, `pathlib`, Linux `/proc` parsers with safe fallbacks on non-Linux test hosts.

---

## Scope

This plan implements the next release-engineering step after M7:

- Real Agent HTTP service.
- Bearer token authorization.
- File list, size, rename, download chunk, upload chunk, merge, verify.
- Health, resource snapshot, process list, process detail.
- Agent packaging files: systemd unit, example env, tarball build script.
- Local HTTP smoke test using a temporary root directory.

This plan does not implement public network exposure, SSH tunneling automation, production signing, or a compiled binary wrapper.

## File Structure

- Create: `agent/filezall_agent/__init__.py`
- Create: `agent/filezall_agent/config.py`
- Create: `agent/filezall_agent/files.py`
- Create: `agent/filezall_agent/resources.py`
- Create: `agent/filezall_agent/server.py`
- Create: `agent/systemd/filezall-agent.service`
- Create: `agent/env/filezall-agent.env.example`
- Create: `agent/build-package.ps1`
- Create: `agent/build-package.sh`
- Create: `tests/agent/test_agent_files.py`
- Create: `tests/agent/test_agent_resources.py`
- Create: `tests/agent/test_agent_http.py`
- Modify: `pyproject.toml` to include the Agent package and script entry point.

## Task 1: Agent File and Transfer Services

**Files:**
- Create: `agent/filezall_agent/config.py`
- Create: `agent/filezall_agent/files.py`
- Test: `tests/agent/test_agent_files.py`

- [ ] **Step 1: Write failing file-service tests**

Create tests that instantiate `AgentConfig(root=tmp_path, token="secret")` and `AgentFileService`. Assert safe root resolution, file listing, file size, chunk write, status query, merge, download chunk, rename, and checksum verification.

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/agent/test_agent_files.py -v
```

Expected: `ModuleNotFoundError: No module named 'filezall_agent'`.

- [ ] **Step 3: Implement file service**

Implement `AgentConfig` and `AgentFileService` with temp chunk storage under `<root>/.filezall-agent/transfers/<transfer_id>/`. Root mode strips a leading slash and keeps all operations inside `root`; production mode can be created without `root` to use absolute paths.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/agent/test_agent_files.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add agent/filezall_agent/config.py agent/filezall_agent/files.py tests/agent/test_agent_files.py
git commit -m "feat: add Agent file transfer service"
```

## Task 2: Agent Resource and Process Services

**Files:**
- Create: `agent/filezall_agent/resources.py`
- Test: `tests/agent/test_agent_resources.py`

- [ ] **Step 1: Write failing resource-service tests**

Create tests for parsing `/proc/meminfo`, `/proc/stat`, process status fields, and fallback snapshots on the current host. Assert returned payloads use the JSON keys expected by `AgentHttpClient`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/agent/test_agent_resources.py -v
```

Expected: `ModuleNotFoundError: No module named 'filezall_agent.resources'`.

- [ ] **Step 3: Implement resource service**

Implement `AgentResourceService` with `resources()`, `processes()`, and `process_detail(pid)`. Use `/proc` when available and return safe zero/empty fallbacks otherwise so tests pass on Windows.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/agent/test_agent_resources.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add agent/filezall_agent/resources.py tests/agent/test_agent_resources.py
git commit -m "feat: add Agent resource service"
```

## Task 3: Agent HTTP Server

**Files:**
- Create: `agent/filezall_agent/__init__.py`
- Create: `agent/filezall_agent/server.py`
- Test: `tests/agent/test_agent_http.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write failing HTTP tests**

Create tests that start the Agent HTTP server on `127.0.0.1:0` with a temporary root and token. Assert unauthorized requests return 401 and authorized requests cover `/health`, `/files/list`, upload chunk, merge, size, download chunk, rename, verify, `/resources`, `/processes`, and `/processes/<pid>`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/agent/test_agent_http.py -v
```

Expected: `ModuleNotFoundError: No module named 'filezall_agent.server'`.

- [ ] **Step 3: Implement HTTP server**

Implement `create_server(config)` returning a `ThreadingHTTPServer`. Add CLI `main()` that reads `FILEZALL_AGENT_TOKEN`, `FILEZALL_AGENT_HOST`, `FILEZALL_AGENT_PORT`, and optional `FILEZALL_AGENT_ROOT`.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/agent/test_agent_http.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add agent/filezall_agent/__init__.py agent/filezall_agent/server.py pyproject.toml tests/agent/test_agent_http.py
git commit -m "feat: add real Agent HTTP server"
```

## Task 4: Agent Packaging Files

**Files:**
- Create: `agent/systemd/filezall-agent.service`
- Create: `agent/env/filezall-agent.env.example`
- Create: `agent/build-package.ps1`
- Create: `agent/build-package.sh`
- Test: `tests/agent/test_agent_packaging.py`

- [ ] **Step 1: Write failing packaging tests**

Create tests asserting service/env/build files exist and contain `FILEZALL_AGENT_TOKEN`, `filezall-agent`, `tar`, and `systemd`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/agent/test_agent_packaging.py -v
```

Expected: file existence assertions fail.

- [ ] **Step 3: Add packaging files**

Add systemd unit, env example, PowerShell package builder, and shell package builder. Both builders create `dist/filezall-agent.tar.gz`.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/agent/test_agent_packaging.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add agent/systemd agent/env agent/build-package.ps1 agent/build-package.sh tests/agent/test_agent_packaging.py
git commit -m "build: add Agent package scaffolding"
```

## Task 5: Full M8 Verification

- [ ] **Step 1: Run all tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Expected: all tests pass except the optional live SFTP skip.

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

- Spec coverage: Real Agent endpoints, token auth, file/chunk operations, resource/process operations, and package files are covered.
- Out of scope: Remote SSH install execution against a real host and public release signing remain release tasks.
- Placeholder scan: No placeholders; tasks name concrete files and verification commands.
- Type consistency: Agent JSON shapes match existing `AgentHttpClient`, `AgentHttpFileClient`, and `AgentTransferClient`.
