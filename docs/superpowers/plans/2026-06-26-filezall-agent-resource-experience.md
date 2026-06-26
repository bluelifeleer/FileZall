# FileZall Agent And Resource Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace binary Agent feedback with a clear Agent status card and improve resource monitoring interaction.

**Architecture:** Model Agent UI states in core or desktop-neutral code, keep install/update/uninstall execution in the existing Agent deployment service, and render the state card in `MainWindow`. Keep resource charts in the existing `ResourceUsageChart` path and extend it instead of adding another chart framework.

**Tech Stack:** Python 3.12, PySide6, pytest, pytest-qt, existing Agent HTTP and resource models.

---

### Task 1: Agent State Model

**Files:**
- Create: `src/filezall_core/agent_status.py`
- Modify: `src/filezall_desktop/controller.py`
- Test: `tests/core/test_agent_status.py`
- Test: `tests/desktop/test_controller.py`

- [x] **Step 1: Write failing Agent state tests**

Test states: unknown, not installed, installing, installed, outdated, unhealthy, update available, uninstalling, and unavailable.

- [x] **Step 2: Verify tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_agent_status.py -q`

Expected: fail because the model does not exist.

- [x] **Step 3: Implement Agent state**

Create `AgentStatus` enum and a `AgentStatusViewModel` dataclass with `state`, `version`, `message`, `primary_action`, and `danger_action`.

- [x] **Step 4: Wire detection result mapping**

Map install detection, health, version, and errors to the view model.

- [x] **Step 5: Verify Agent state tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_agent_status.py tests\desktop\test_controller.py::test_controller_maps_agent_detection_to_status_view_model -q`

Expected: pass.

### Task 2: Agent Status Card

**Files:**
- Create: `src/filezall_desktop/agent_status_card.py`
- Modify: `src/filezall_desktop/main_window.py`
- Modify: `src/filezall_desktop/i18n.py`
- Test: `tests/desktop/test_agent_status_card.py`
- Test: `tests/desktop/test_main_window.py`

- [x] **Step 1: Write failing UI tests**

Test that the card displays not installed, installed, outdated, unhealthy, update, reinstall, and uninstall actions with distinct button roles.

- [x] **Step 2: Verify tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_agent_status_card.py -q`

Expected: fail because the widget does not exist.

- [x] **Step 3: Implement status card**

Create a compact card with state label, version label, message label, primary action button, and uninstall button.

- [x] **Step 4: Replace scattered Agent status UI**

Keep the top Agent button for quick access but make the resource panel card the authoritative visual state.

- [x] **Step 5: Verify UI tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_agent_status_card.py tests\desktop\test_main_window.py::test_main_window_updates_agent_status_card -q`

Expected: pass.

### Task 3: Agent Operation Step Panel

**Files:**
- Modify: `src/filezall_desktop/agent_status_card.py`
- Modify: `src/filezall_desktop/main_window.py`
- Test: `tests/desktop/test_agent_status_card.py`
- Test: `tests/desktop/test_main_window.py`

- [x] **Step 1: Write failing progress tests**

Test that install/update/uninstall progress appears as ordered step rows and final success/failure state is visible without opening logs.

- [x] **Step 2: Verify tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_agent_status_card.py::test_agent_card_shows_operation_steps -q`

Expected: fail because progress rows are not rendered.

- [x] **Step 3: Add operation steps**

Render each progress callback line as a step row. Keep the full log in the log panel.

- [x] **Step 4: Verify progress tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_agent_status_card.py::test_agent_card_shows_operation_steps tests\desktop\test_main_window.py::test_agent_install_progress_updates_status_card -q`

Expected: pass.

### Task 4: Resource Chart Interaction

**Files:**
- Modify: `src/filezall_desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [x] **Step 1: Write failing chart tests**

Test time range controls, hover details, network curves, disk partition selector, and process sort/filter controls.

- [x] **Step 2: Verify tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_resource_monitor_has_time_range_and_process_filters -q`

Expected: fail because controls are missing.

- [x] **Step 3: Add chart controls**

Add time ranges `1m`, `5m`, `15m`, `1h`, disk partition selector, process sort selector, and process filter input.

- [x] **Step 4: Verify chart tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_resource_monitor_has_time_range_and_process_filters -q`

Expected: pass.

### Task 5: Commit

- [x] **Step 1: Run focused tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_agent_status.py tests\desktop\test_agent_status_card.py tests\desktop\test_main_window.py tests\desktop\test_controller.py`

Expected: pass.

- [x] **Step 2: Run full tests**

Run: `.\.venv\Scripts\python.exe -m pytest`

Expected: pass, with live SFTP skipped when environment variables are absent.

- [x] **Step 3: Commit**

Run:

```powershell
git add src tests docs
git commit -m "Improve Agent and resource experience"
```
