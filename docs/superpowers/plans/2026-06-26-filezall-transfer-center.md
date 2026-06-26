# FileZall Transfer Center Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the queue area into a transfer center with speed, remaining time, retries, failure reasons, concurrency, limit controls, and clear weak-network states.

**Architecture:** Keep transfer state in core queue models and repositories. Add runtime metrics to queue execution and render them in the desktop transfer table. UI controls update queue settings rather than directly mutating transfer items.

**Tech Stack:** Python 3.12, PySide6, SQLite, pytest, pytest-qt.

---

### Task 1: Transfer Metrics Model

**Files:**
- Modify: `src/filezall_core/models.py`
- Modify: `src/filezall_core/transfer_repository.py`
- Modify: `src/filezall_core/queue.py`
- Test: `tests/core/test_queue.py`
- Test: `tests/core/test_transfer_repository.py`

- [x] **Step 1: Write failing metrics tests**

Test that a running item records `started_at`, `updated_at`, `bytes_per_second`, `remaining_seconds`, `retry_count`, and `failure_reason`.

- [x] **Step 2: Verify tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_queue.py::test_queue_records_transfer_metrics -q`

Expected: fail because metrics fields are missing.

- [x] **Step 3: Add fields and persistence**

Add fields to `TransferItem` with defaults. Add SQLite columns using migration-safe `alter table` checks.

- [x] **Step 4: Calculate metrics**

In queue progress callbacks, calculate speed from elapsed time and remaining time from total size minus transferred bytes.

- [x] **Step 5: Verify core metrics tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_queue.py tests\core\test_transfer_repository.py -q`

Expected: pass.

### Task 2: Transfer Center UI

**Files:**
- Modify: `src/filezall_desktop/main_window.py`
- Modify: `src/filezall_desktop/i18n.py`
- Test: `tests/desktop/test_main_window.py`

- [x] **Step 1: Write failing UI tests**

Test that the transfer table shows speed, remaining time, retry count, and failure reason columns.

- [x] **Step 2: Verify tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_transfer_center_shows_metrics_columns -q`

Expected: fail because the columns are not present.

- [x] **Step 3: Add columns and formatting**

Use human-readable speed, time, and failure text. Keep table compact.

- [x] **Step 4: Verify UI tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_transfer_center_shows_metrics_columns -q`

Expected: pass.

### Task 3: Concurrency And Limit Controls

**Files:**
- Modify: `src/filezall_core/queue.py`
- Create: `src/filezall_core/transfer_settings.py`
- Modify: `src/filezall_desktop/main_window.py`
- Test: `tests/core/test_queue.py`
- Test: `tests/desktop/test_main_window.py`

- [x] **Step 1: Write failing settings tests**

Test max concurrent transfers and byte-per-second limit settings are stored and used when queue execution starts.

- [x] **Step 2: Verify tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_queue.py::test_queue_respects_concurrency_limit -q`

Expected: fail because concurrency controls are missing.

- [x] **Step 3: Add settings model**

Create `TransferSettings(max_concurrent=2, bytes_per_second_limit=None)`.

- [x] **Step 4: Add desktop controls**

Add compact controls above the transfer table for concurrency and limit. Use spin boxes, not plain text.

- [x] **Step 5: Verify settings tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_queue.py::test_queue_respects_concurrency_limit tests\desktop\test_main_window.py::test_transfer_center_has_concurrency_and_limit_controls -q`

Expected: pass.

### Task 4: Weak Network And Retry States

**Files:**
- Modify: `src/filezall_core/queue.py`
- Modify: `src/filezall_desktop/main_window.py`
- Test: `tests/core/test_queue.py`
- Test: `tests/desktop/test_main_window.py`

- [x] **Step 1: Write failing retry tests**

Test that failed transfers move through retrying state with retry count and failure reason, then either complete or fail visibly.

- [x] **Step 2: Verify tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_queue.py::test_queue_records_retry_state_and_failure_reason -q`

Expected: fail because retry state is not modeled.

- [x] **Step 3: Add retry state handling**

Add retry count and failure reason updates around transfer exceptions. Keep retry policy conservative: three attempts by default.

- [x] **Step 4: Render retry and failure state**

Show status text and row color for waiting, running, paused, retrying, failed, and completed.

- [x] **Step 5: Verify retry tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_queue.py::test_queue_records_retry_state_and_failure_reason tests\desktop\test_main_window.py::test_transfer_center_renders_retry_and_failure_reason -q`

Expected: pass.

### Task 5: Commit

- [x] **Step 1: Run focused tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_queue.py tests\core\test_transfer_repository.py tests\desktop\test_main_window.py`

Expected: pass.

- [x] **Step 2: Run full tests**

Run: `.\.venv\Scripts\python.exe -m pytest`

Expected: pass, with live SFTP skipped when environment variables are absent.

- [x] **Step 3: Commit**

Run:

```powershell
git add src tests docs
git commit -m "Upgrade transfer center"
```
