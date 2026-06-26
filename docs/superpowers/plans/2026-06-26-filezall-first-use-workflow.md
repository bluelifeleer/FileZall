# FileZall First-Use Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing Getting Started guide into an actionable first-run workflow for connection testing, folder setup, optional Agent install, and saving the successful site.

**Architecture:** Keep connection execution inside `MainWindowController`. Add a focused onboarding model and dialog layer in `src/filezall_desktop/onboarding.py`; `MainWindow` wires the dialog to existing connection, path, and Agent actions. Store first-run dismissal through the existing app settings table if settings access already exists; otherwise add a small settings repository in core.

**Tech Stack:** Python 3.12, PySide6, pytest-qt, existing site repository, credential service, and Agent installer.

---

### Task 1: First-Run State

**Files:**
- Modify: `src/filezall_core/storage.py`
- Create: `src/filezall_core/settings_repository.py`
- Test: `tests/core/test_settings_repository.py`

- [ ] **Step 1: Write failing settings tests**

Test that `SettingsRepository.get_bool("onboarding.dismissed", False)` returns `False`, then `set_bool("onboarding.dismissed", True)` persists `True` across repository instances.

- [ ] **Step 2: Verify the test fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_settings_repository.py -q`

Expected: fail because `SettingsRepository` does not exist.

- [ ] **Step 3: Implement settings repository**

Create a small repository backed by the existing `app_settings` table with `get`, `set`, `get_bool`, and `set_bool`.

- [ ] **Step 4: Verify core tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_settings_repository.py tests\core\test_storage.py -q`

Expected: pass.

### Task 2: Launch-Time Guide

**Files:**
- Modify: `src/filezall_desktop/app.py`
- Modify: `src/filezall_desktop/main_window.py`
- Modify: `src/filezall_desktop/onboarding.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write failing UI tests**

Add tests that a non-dismissed first-run state opens the guide after startup, and a dismissed state does not.

- [ ] **Step 2: Verify the tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_first_run_guide_opens_when_not_dismissed tests\desktop\test_main_window.py::test_first_run_guide_stays_closed_after_dismissal -q`

Expected: fail because `MainWindow` does not accept onboarding settings.

- [ ] **Step 3: Add dialog controls**

Add `Do not show again`, `Start Setup`, and `Close` controls to `GettingStartedDialog`. Emit `dismissed_changed` when the checkbox changes.

- [ ] **Step 4: Wire startup behavior**

Pass `SettingsRepository` from `app.py` into `MainWindow`. On first startup, call `show_getting_started()` with a zero-delay `QTimer.singleShot(0, ...)` if `onboarding.dismissed` is false.

- [ ] **Step 5: Verify desktop tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_first_run_guide_opens_when_not_dismissed tests\desktop\test_main_window.py::test_first_run_guide_stays_closed_after_dismissal -q`

Expected: pass.

### Task 3: Connection Test And Failure Guidance

**Files:**
- Modify: `src/filezall_desktop/controller.py`
- Modify: `src/filezall_desktop/onboarding.py`
- Modify: `src/filezall_desktop/main_window.py`
- Test: `tests/desktop/test_controller.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write failing controller tests**

Add tests for classifying connection errors into bad credentials, unreachable host or port, permission denied, systemd unsupported, Agent missing, Agent unhealthy, and unknown failure.

- [ ] **Step 2: Verify the controller tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_controller.py::test_controller_classifies_connection_errors -q`

Expected: fail because the classifier is not exposed for connection failures.

- [ ] **Step 3: Implement classification**

Add `classify_connection_error(message: str) -> str` in `controller.py` or a small core module. Reuse existing `classify_agent_error` for Agent/systemd messages.

- [ ] **Step 4: Add Test Connection action**

Add a guide action that calls `controller.connect_for_window(...)` without saving the site when possible, renders success/failure status in the guide, and does not duplicate full connect UI logic.

- [ ] **Step 5: Verify focused tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_controller.py::test_controller_classifies_connection_errors tests\desktop\test_main_window.py::test_getting_started_test_connection_shows_clear_failure -q`

Expected: pass.

### Task 4: Save Successful Setup

**Files:**
- Modify: `src/filezall_desktop/onboarding.py`
- Modify: `src/filezall_desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write failing save-flow tests**

Test that after a successful connection, the guide offers `Save Site`, calls existing connect/save behavior with `remember_secret=True`, and refreshes the site selector.

- [ ] **Step 2: Verify the save-flow tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_getting_started_saves_successful_site -q`

Expected: fail because the guide does not expose save flow.

- [ ] **Step 3: Implement save flow**

Use existing `_handle_connect_clicked` behavior and `remember_secret_confirmer`; show the credential-manager explanation before saving secrets.

- [ ] **Step 4: Verify milestone**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py tests\desktop\test_app_bootstrap.py`

Expected: pass.

### Task 5: Commit

**Files:**
- All files changed by Tasks 1-4.

- [ ] **Step 1: Run full tests**

Run: `.\.venv\Scripts\python.exe -m pytest`

Expected: pass, with live SFTP skipped when environment variables are absent.

- [ ] **Step 2: Commit**

Run:

```powershell
git add src tests docs
git commit -m "Improve first-use workflow"
```
