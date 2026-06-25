# FileZall M5 Agent and Resource Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add testable Linux Agent health/resource APIs, SSH deployment orchestration, core resource-monitoring models, and a desktop resource panel with process-detail expansion.

**Architecture:** Resource monitoring stays in `filezall_core` behind provider-style classes. Agent HTTP and SSH deployment are implemented with injected transports so tests do not require a real server. The desktop UI renders snapshots and process details through controller methods, without running background polling in M5.

**Tech Stack:** Python 3.12, pytest, dataclasses, stdlib `json` and `urllib`, PySide6, existing `SiteProfile` and `Protocol` models.

---

## Scope

This plan implements M5 from `docs/superpowers/specs/2026-06-24-filezall-design.md`:

- Agent health check.
- SSH deployment flow orchestration.
- CPU, memory, disk, and network resource snapshot models.
- Process list and process detail models.
- Desktop resource monitor panel with refresh and process detail actions.

This plan does not implement periodic polling, SSH tunneling, a real packaged Linux Agent binary, system tray notifications, or Agent HTTP chunked transfer. Chunked transfer is M6.

## File Structure

- Create: `src/filezall_core/resource_models.py` - resource and process dataclasses.
- Create: `src/filezall_core/agent_client.py` - HTTP Agent client with injected opener.
- Create: `src/filezall_core/agent_deployment.py` - SSH deployment command orchestration.
- Create: `src/filezall_core/resource_monitor.py` - provider selection and unavailable-provider behavior.
- Modify: `src/filezall_desktop/controller.py` - expose `refresh_resources()` and `show_process_detail(pid)`.
- Modify: `src/filezall_desktop/main_window.py` - add resource panel and wire refresh/detail.
- Create: `tests/core/test_resource_models.py`.
- Create: `tests/core/test_agent_client.py`.
- Create: `tests/core/test_agent_deployment.py`.
- Create: `tests/core/test_resource_monitor.py`.
- Modify: `tests/desktop/test_controller.py`.
- Modify: `tests/desktop/test_main_window.py`.

## Task 1: Resource Models

**Files:**
- Create: `src/filezall_core/resource_models.py`
- Test: `tests/core/test_resource_models.py`

- [ ] **Step 1: Write failing model tests**

Create tests that import `ResourceSnapshot`, `CpuStats`, `MemoryStats`, `DiskUsage`, `NetworkStats`, `ProcessSummary`, and `ProcessDetail`, instantiate them, and assert the fields round-trip.

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_resource_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'filezall_core.resource_models'`.

- [ ] **Step 3: Implement frozen dataclasses**

Create frozen dataclasses for CPU percent, memory total/used/available, disk mount usage, network rx/tx rate, process summary, process detail, and a snapshot containing all collections.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_resource_models.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/resource_models.py tests/core/test_resource_models.py
git commit -m "feat: add resource monitoring models"
```

## Task 2: Agent HTTP Client

**Files:**
- Create: `src/filezall_core/agent_client.py`
- Test: `tests/core/test_agent_client.py`

- [ ] **Step 1: Write failing Agent client tests**

Create tests with a fake opener whose `open(request, timeout)` returns JSON bytes for `/health`, `/resources`, `/processes`, and `/processes/<pid>`. Assert:

- `health()` returns `True` when JSON contains `{"ok": true}`.
- `resource_snapshot()` maps JSON into `ResourceSnapshot`.
- `processes()` maps rows into `ProcessSummary`.
- `process_detail(pid)` maps one row into `ProcessDetail`.
- Requests include `Authorization: Bearer <token>`.

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_agent_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'filezall_core.agent_client'`.

- [ ] **Step 3: Implement Agent client**

Create `AgentHttpClient(base_url, token, opener=None, timeout=10)`. Use `urllib.request.Request`; parse JSON; convert process/detail/snapshot payloads into `resource_models` dataclasses.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_agent_client.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/agent_client.py tests/core/test_agent_client.py
git commit -m "feat: add Agent HTTP resource client"
```

## Task 3: SSH Agent Deployment Flow

**Files:**
- Create: `src/filezall_core/agent_deployment.py`
- Test: `tests/core/test_agent_deployment.py`

- [ ] **Step 1: Write failing deployment tests**

Create a fake runner with `upload(local_path, remote_path)` and `run(command)` call capture. Assert `AgentInstaller.install_or_update(package_path, token)` uploads the package and runs commands to create `/opt/filezall-agent`, extract package, write config, install service, restart service, and check health.

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_agent_deployment.py -v
```

Expected: `ModuleNotFoundError: No module named 'filezall_core.agent_deployment'`.

- [ ] **Step 3: Implement installer orchestration**

Create `AgentInstaller(runner)` with `install_or_update(package_path, token)`. Return an `AgentInstallResult(success=True, commands_run=<count>)` when all commands complete.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_agent_deployment.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/agent_deployment.py tests/core/test_agent_deployment.py
git commit -m "feat: add Agent deployment orchestration"
```

## Task 4: Resource Monitor Service

**Files:**
- Create: `src/filezall_core/resource_monitor.py`
- Test: `tests/core/test_resource_monitor.py`

- [ ] **Step 1: Write failing monitor-service tests**

Create tests that assert:

- For an Agent-enabled site, `ResourceMonitorService` delegates snapshot/process/detail calls to an injected provider.
- For FTP/FTPS sites without Agent, calls raise `ResourceMonitoringUnavailable`.
- For SFTP without Agent, an injected SSH provider can be used.

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_resource_monitor.py -v
```

Expected: `ModuleNotFoundError: No module named 'filezall_core.resource_monitor'`.

- [ ] **Step 3: Implement monitor service**

Create `ResourceMonitorService(agent_provider_factory, ssh_provider_factory=None)` with `snapshot(site)`, `processes(site)`, and `process_detail(site, pid)`. Raise `ResourceMonitoringUnavailable` for FTP/FTPS without Agent and for SFTP without SSH provider.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_resource_monitor.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/resource_monitor.py tests/core/test_resource_monitor.py
git commit -m "feat: add resource monitor service"
```

## Task 5: Desktop Resource Panel

**Files:**
- Modify: `src/filezall_desktop/controller.py`
- Modify: `src/filezall_desktop/main_window.py`
- Test: `tests/desktop/test_controller.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write failing desktop tests**

Add tests that assert:

- `MainWindow.set_resource_snapshot(snapshot)` fills CPU, memory, disk, network labels and process rows.
- Selecting a process row and clicking detail calls `controller.show_process_detail(pid)`.
- `MainWindow.set_process_detail(detail)` displays command line, user, thread count, and status.
- `MainWindowController.refresh_resources()` delegates to an injected resource monitor using the connected site and calls `window.set_resource_snapshot`.
- `MainWindowController.show_process_detail(pid)` delegates and calls `window.set_process_detail`.

- [ ] **Step 2: Run desktop tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/desktop/test_main_window.py tests/desktop/test_controller.py -v
```

Expected: failures for missing resource panel methods and controller actions.

- [ ] **Step 3: Implement desktop resource panel**

Add a compact `Resource Monitor` section below the transfer table with refresh/detail buttons, labels for CPU/memory/disk/network, a process table, and a process-detail label. Controller stores the connected site and uses injected `resource_monitor_service`.

- [ ] **Step 4: Run desktop tests to verify they pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/desktop/test_main_window.py tests/desktop/test_controller.py -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_desktop/controller.py src/filezall_desktop/main_window.py tests/desktop/test_controller.py tests/desktop/test_main_window.py
git commit -m "feat: add desktop resource monitor panel"
```

## Task 6: Full M5 Verification

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

- Spec coverage: Agent health, deployment orchestration, resource snapshot, process list, process detail, and desktop display are covered.
- Out of scope: Background polling, SSH tunneling, real Agent package generation, and chunked Agent transfer are deferred to M6.
- Placeholder scan: No placeholders; each task lists concrete files, tests, and commands.
- Type consistency: Desktop methods consume dataclasses from `resource_models.py`; controller delegates through `ResourceMonitorService`.
