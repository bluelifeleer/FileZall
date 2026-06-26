# FileZall Logs And Diagnostics Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Categorize logs, make errors actionable, support copy/export, and ensure diagnostics are useful and redacted.

**Architecture:** Extend the existing `TransferLogService` into categorized log records while preserving plain text export. Keep redaction in core so UI and diagnostics share the same behavior.

**Tech Stack:** Python 3.12, PySide6, zipfile diagnostics, pytest, pytest-qt.

---

### Task 1: Categorized Log Records

**Files:**
- Modify: `src/filezall_core/log_service.py`
- Modify: `src/filezall_core/diagnostics.py`
- Test: `tests/core/test_log_service.py`
- Test: `tests/core/test_diagnostics.py`

- [ ] **Step 1: Write failing log category tests**

Test categories: connection, transfer, Agent, resource, and error. Test plain export preserves readable lines.

- [ ] **Step 2: Verify tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_log_service.py::test_log_service_records_categories -q`

Expected: fail because categories are not modeled.

- [ ] **Step 3: Add log record model**

Add `LogRecord(timestamp, category, level, message)` and keep `append(message)` as a compatibility wrapper using category `transfer`.

- [ ] **Step 4: Update diagnostics**

Include categorized log export and runtime logs in diagnostics.

- [ ] **Step 5: Verify core log tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_log_service.py tests\core\test_diagnostics.py -q`

Expected: pass.

### Task 2: Redaction Coverage

**Files:**
- Create: `src/filezall_core/redaction.py`
- Modify: `src/filezall_core/log_service.py`
- Modify: `src/filezall_core/diagnostics.py`
- Test: `tests/core/test_redaction.py`

- [ ] **Step 1: Write failing redaction tests**

Test redaction of password values, token values, bearer headers, private key paths, and Agent token refs.

- [ ] **Step 2: Verify tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_redaction.py -q`

Expected: fail because centralized redaction does not exist.

- [ ] **Step 3: Implement redaction**

Create `redact_sensitive(text: str) -> str` and call it from log append and diagnostics export.

- [ ] **Step 4: Verify redaction tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_redaction.py tests\core\test_log_service.py tests\core\test_diagnostics.py -q`

Expected: pass.

### Task 3: Log Viewer UI

**Files:**
- Create: `src/filezall_desktop/log_viewer.py`
- Modify: `src/filezall_desktop/main_window.py`
- Modify: `src/filezall_desktop/i18n.py`
- Test: `tests/desktop/test_log_viewer.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write failing UI tests**

Test category tabs or filter chips, error copy button, export logs, and export diagnostics.

- [ ] **Step 2: Verify tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_log_viewer.py -q`

Expected: fail because log viewer widget does not exist.

- [ ] **Step 3: Implement log viewer**

Render category filters, a log table/list, copy selected error, export logs, and export diagnostics actions.

- [ ] **Step 4: Wire existing logs**

Replace direct plain text log rendering with `LogViewer`, keeping existing `append_log` behavior.

- [ ] **Step 5: Verify UI tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_log_viewer.py tests\desktop\test_main_window.py::test_main_window_filters_log_categories -q`

Expected: pass.

### Task 4: Commit

- [ ] **Step 1: Run focused tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_log_service.py tests\core\test_redaction.py tests\core\test_diagnostics.py tests\desktop\test_log_viewer.py tests\desktop\test_main_window.py`

Expected: pass.

- [ ] **Step 2: Run full tests**

Run: `.\.venv\Scripts\python.exe -m pytest`

Expected: pass, with live SFTP skipped when environment variables are absent.

- [ ] **Step 3: Commit**

Run:

```powershell
git add src tests docs
git commit -m "Improve logs and diagnostics experience"
```
