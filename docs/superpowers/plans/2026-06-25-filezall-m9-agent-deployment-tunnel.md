# FileZall M9 Agent Deployment Tunnel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the practical Agent deployment loop by adding SSH tunnel lifecycle modeling, install health verification, and operator-facing deployment notes.

**Architecture:** Keep tunnel and install orchestration in `filezall_core` so the desktop UI can trigger it without owning shell commands. The SSH implementation remains protocol-agnostic through runner protocols, letting tests verify exact behavior without opening real network connections.

**Tech Stack:** Python 3.12, pytest, existing `AgentInstaller`, stdlib dataclasses/protocols, existing Agent HTTP client contracts.

---

## Scope

This plan implements the next production-readiness step after M8:

- Agent local tunnel lifecycle helpers.
- Agent install/update health verification using an injected health checker.
- Documentation for building, installing, tunneling, and validating the Agent package.

This plan does not run commands against a real Linux host, create signed installers, or require live network credentials.

## File Structure

- Create: `src/filezall_core/agent_tunnel.py`
- Modify: `src/filezall_core/agent_deployment.py`
- Create: `tests/core/test_agent_tunnel.py`
- Modify: `tests/core/test_agent_deployment.py`
- Create: `docs/agent-deployment.md`
- Modify: `packaging/README.md`

## Task 1: Agent Tunnel Lifecycle

**Files:**
- Create: `src/filezall_core/agent_tunnel.py`
- Test: `tests/core/test_agent_tunnel.py`

- [ ] **Step 1: Write failing tunnel tests**

Create tests for a runner-backed `AgentTunnelManager` that starts an SSH local-forward command, returns the local Agent URL, reports active tunnel state, and stops the tunnel handle.

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_agent_tunnel.py -v
```

Expected: `ModuleNotFoundError: No module named 'filezall_core.agent_tunnel'`.

- [ ] **Step 3: Implement tunnel manager**

Create `AgentTunnelManager(runner)` with `open(site, local_port=0, remote_host="127.0.0.1", remote_port=8765)`, `active()`, and `close()`. The runner protocol exposes `start(command: list[str]) -> AgentTunnelHandle`; the handle exposes `local_port`, `is_running()`, and `stop()`.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_agent_tunnel.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/agent_tunnel.py tests/core/test_agent_tunnel.py
git commit -m "feat: add Agent tunnel manager"
```

## Task 2: Install Health Verification

**Files:**
- Modify: `src/filezall_core/agent_deployment.py`
- Modify: `tests/core/test_agent_deployment.py`

- [ ] **Step 1: Write failing install-verification test**

Add a test that passes a health checker returning `True` and asserts `AgentInstaller.install_or_update()` records `verified=True`. Add a second test where the health checker returns `False` and assert `success=False`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_agent_deployment.py -v
```

Expected: `TypeError` or assertion failure because `AgentInstaller` has no health checker and result has no `verified`.

- [ ] **Step 3: Implement health verification**

Extend `AgentInstallResult` with `verified: bool`. Extend `AgentInstaller.__init__(runner, health_check=None)`. After installation commands, call `health_check()` when provided. Return `success=True, verified=True` only when the checker passes; return `success=False, verified=False` when the checker fails.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_agent_deployment.py -v
```

Expected: all deployment tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/agent_deployment.py tests/core/test_agent_deployment.py
git commit -m "feat: verify Agent install health"
```

## Task 3: Agent Deployment Documentation

**Files:**
- Create: `docs/agent-deployment.md`
- Modify: `packaging/README.md`

- [ ] **Step 1: Write failing docs test**

Add assertions to packaging tests or a new docs test that require `docs/agent-deployment.md` to mention `FILEZALL_AGENT_TOKEN`, `filezall-agent`, `systemctl`, `ssh -L`, and `health`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_packaging_files.py -v
```

Expected: file existence assertion fails.

- [ ] **Step 3: Add deployment documentation**

Create `docs/agent-deployment.md` with package build, Linux install/update, systemd operation, SSH tunnel, health check, and troubleshooting sections. Link it from `packaging/README.md`.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_packaging_files.py -v
```

Expected: all packaging docs tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add docs/agent-deployment.md packaging/README.md tests/test_packaging_files.py
git commit -m "docs: add Agent deployment guide"
```

## Task 4: Full M9 Verification

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

Expected: no output after commits and smoke cleanup.

## Self-Review

- Spec coverage: This plan covers the M8 out-of-scope production bridge: SSH tunneling, install verification, and deployment guidance.
- Placeholder scan: No placeholders or TODO markers are used.
- Type consistency: Tunnel and deployment protocols use existing `SiteProfile` and Agent HTTP health semantics.
