# FileZall File Operations Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make local and remote file operations complete, symmetric, and clear, including conflict policies, drag transfer, and recursive directory progress.

**Architecture:** Keep protocol-specific operations in core adapters and session classes. Add conflict and recursive-planning models in core; keep UI prompts in desktop. Reuse the transfer queue for recursive upload/download items.

**Tech Stack:** Python 3.12, PySide6 drag/drop, pathlib, PurePosixPath, pytest, pytest-qt.

---

### Task 1: Conflict Policy Prompt

**Files:**
- Modify: `src/filezall_core/models.py`
- Create: `src/filezall_desktop/conflict_dialog.py`
- Modify: `src/filezall_desktop/main_window.py`
- Test: `tests/desktop/test_conflict_dialog.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write failing tests**

Test that the dialog offers overwrite, skip, rename, newer-only, and apply-to-all. Test that upload/download asks for a conflict policy when the destination exists.

- [ ] **Step 2: Verify tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_conflict_dialog.py tests\desktop\test_main_window.py::test_upload_prompts_for_conflict_policy -q`

Expected: fail because conflict prompt is absent.

- [ ] **Step 3: Add model values**

Ensure `ConflictPolicy` has `OVERWRITE`, `SKIP`, `RENAME`, and `NEWER_ONLY`. Add `apply_to_all` only to the dialog result, not the persisted task model.

- [ ] **Step 4: Implement dialog and wiring**

Use a small modal dialog with radio buttons and an apply-to-all checkbox. Pass the selected policy into queue task creation.

- [ ] **Step 5: Verify prompt tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_conflict_dialog.py tests\desktop\test_main_window.py::test_upload_prompts_for_conflict_policy -q`

Expected: pass.

### Task 2: Recursive Directory Planning

**Files:**
- Create: `src/filezall_core/directory_plan.py`
- Modify: `src/filezall_core/protocols.py`
- Modify: `src/filezall_core/sftp_adapter.py`
- Modify: `src/filezall_core/ftp_adapter.py`
- Modify: `src/filezall_core/agent_file_client.py`
- Test: `tests/core/test_directory_plan.py`
- Test: adapter tests under `tests/core`

- [ ] **Step 1: Write failing core tests**

Test local recursive planning returns total files, total bytes, and relative paths. Test remote planning can walk nested directories through the `RemoteFileClient` boundary.

- [ ] **Step 2: Verify tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_directory_plan.py -q`

Expected: fail because directory planning does not exist.

- [ ] **Step 3: Add remote recursive listing boundary**

Add `walk_directory(path)` to `RemoteFileClient` and implement it by repeated `list_directory()` calls in a shared helper when protocol adapters do not provide an optimized walk.

- [ ] **Step 4: Implement directory plans**

Create `DirectoryTransferPlan` with `root`, `items`, `total_files`, and `total_bytes`. Items carry source, destination, relative path, size, and direction.

- [ ] **Step 5: Verify core recursive tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_directory_plan.py tests\core\test_sftp_adapter.py tests\core\test_ftp_adapter.py tests\core\test_agent_file_client.py -q`

Expected: pass.

### Task 3: Recursive Queue Progress

**Files:**
- Modify: `src/filezall_desktop/controller.py`
- Modify: `src/filezall_desktop/main_window.py`
- Test: `tests/desktop/test_controller.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write failing queue tests**

Test that adding a directory creates one transfer task with multiple items and publishes aggregate progress including total files, total bytes, current file, and completed bytes.

- [ ] **Step 2: Verify tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_controller.py::test_controller_queues_recursive_directory_upload -q`

Expected: fail because directories are not expanded into queue items.

- [ ] **Step 3: Implement queue expansion**

When selected path is a directory, build a `DirectoryTransferPlan`, create one `TransferTask`, and add all items to the queue.

- [ ] **Step 4: Render aggregate progress**

Add a compact summary row or status label in the transfer center for total files, current file, total bytes, and aggregate progress.

- [ ] **Step 5: Verify recursive queue tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_controller.py::test_controller_queues_recursive_directory_upload tests\desktop\test_main_window.py::test_transfer_center_shows_directory_progress -q`

Expected: pass.

### Task 4: Drag Upload And Download

**Files:**
- Modify: `src/filezall_desktop/widgets.py`
- Modify: `src/filezall_desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write failing drag tests**

Test dropping local files on the remote panel calls upload/add-to-queue, and dragging remote rows to the local panel calls download/add-to-queue.

- [ ] **Step 2: Verify tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_dragging_local_files_to_remote_queues_upload -q`

Expected: fail because drag/drop is not wired.

- [ ] **Step 3: Enable drag/drop**

Add drag MIME payloads for local and remote rows. Accept file URLs from the OS for local files. Keep drag behavior disabled for the parent row.

- [ ] **Step 4: Verify drag tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_dragging_local_files_to_remote_queues_upload tests\desktop\test_main_window.py::test_dragging_remote_rows_to_local_queues_download -q`

Expected: pass.

### Task 5: Commit

- [ ] **Step 1: Run focused tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_directory_plan.py tests\desktop\test_conflict_dialog.py tests\desktop\test_controller.py tests\desktop\test_main_window.py`

Expected: pass.

- [ ] **Step 2: Run full tests**

Run: `.\.venv\Scripts\python.exe -m pytest`

Expected: pass, with live SFTP skipped when environment variables are absent.

- [ ] **Step 3: Commit**

Run:

```powershell
git add src tests docs
git commit -m "Improve file operation experience"
```
