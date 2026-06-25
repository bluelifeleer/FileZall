# FileZall M15 Multi-Select Parent Navigation and Heartbeat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add FileZilla-like file list multi-select, parent-directory navigation, and active connection heartbeat status.

**Architecture:** `FilePanel` owns row metadata and multi-selection helpers. `MainWindow` maps selected rows to local/remote paths, supports parent-directory rows, and owns the heartbeat timer/status light. `MainWindowController` exposes a lightweight heartbeat method that verifies the current session can still list the current remote directory.

**Tech Stack:** Python 3.12, PySide6 `QTableWidget`, `QTimer`, pytest-qt.

---

### Task 1: Multi-Select File Rows

**Files:**
- Modify: `src/filezall_desktop/widgets.py`
- Modify: `src/filezall_desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] Write failing tests asserting file panels use `ExtendedSelection`, selected rows can include multiple files, and upload/download/delete/queue actions execute for every selected non-parent row.
- [ ] Run the targeted tests and confirm they fail.
- [ ] Add `selected_names()` and `selected_entries()` helpers to `FilePanel`; update main-window actions to iterate selected names.
- [ ] Run the targeted tests and confirm they pass.

### Task 2: Parent Directory Row

**Files:**
- Modify: `src/filezall_desktop/widgets.py`
- Modify: `src/filezall_desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] Write failing tests asserting `..` appears as the first row for file lists and clicking or double-clicking it navigates to the parent directory.
- [ ] Run the targeted tests and confirm they fail.
- [ ] Add a parent row kind to `FilePanel`; update double-click handling to route parent rows to local/remote parent paths.
- [ ] Run the targeted tests and confirm they pass.

### Task 3: Connection Heartbeat

**Files:**
- Modify: `src/filezall_desktop/controller.py`
- Modify: `src/filezall_desktop/main_window.py`
- Test: `tests/desktop/test_controller.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] Write failing tests asserting the controller heartbeat returns true when the current session lists the current directory and false when it raises, and the window maps heartbeat success/failure to green/red status lights.
- [ ] Run the targeted tests and confirm they fail.
- [ ] Add `MainWindowController.heartbeat()` and a `QTimer` in `MainWindow` that sets yellow while checking, green on success, and red on failure.
- [ ] Run the targeted tests and confirm they pass.

### Task 4: Verification and Packaging

**Files:**
- Generated output under `dist/`

- [ ] Run desktop/controller tests.
- [ ] Run full pytest.
- [ ] Launch source desktop smoke test.
- [ ] Merge to `master` and push.
- [ ] Rebuild Windows portable package.
- [ ] Launch packaged executable smoke test.
