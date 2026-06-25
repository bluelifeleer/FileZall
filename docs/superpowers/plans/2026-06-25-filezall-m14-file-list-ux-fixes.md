# FileZall M14 File List UX Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix file list navigation, selection, log resizing, connection status light, and saved password autofill behavior.

**Architecture:** Keep the changes in the desktop UI layer with minimal controller support for saved secrets. `FilePanel` owns table selection and row metadata. `MainWindow` owns splitters, status light rendering, and saved site autofill. `MainWindowController` exposes saved site loading with optional secret lookup so the UI can fill remembered connection fields.

**Tech Stack:** Python 3.12, PySide6, pytest-qt, existing FileZall core services.

---

### Task 1: File Table Directory Navigation and Full Row Selection

**Files:**
- Modify: `src/filezall_desktop/widgets.py`
- Modify: `src/filezall_desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] Write failing tests showing that file panels use row selection and that double-clicking a directory row on a non-name column enters the directory after lists are reloaded.
- [ ] Run the targeted tests and confirm they fail before code changes.
- [ ] Store directory metadata on every table row, configure full-row single selection, and make `is_dir_at(row)` read row metadata instead of relying on a specific cell.
- [ ] Run the targeted tests and confirm they pass.

### Task 2: Resizable Transfer Logs

**Files:**
- Modify: `src/filezall_desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] Write a failing test asserting Transfer Center exposes a vertical splitter that contains the transfer table and log view.
- [ ] Run the targeted test and confirm it fails.
- [ ] Replace the fixed transfer table/log layout with an internal vertical `QSplitter`.
- [ ] Run the targeted test and confirm it passes.

### Task 3: Bottom Status Light Tooltip

**Files:**
- Modify: `src/filezall_desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] Write failing tests showing the status indicator displays a small light without status text and exposes the status text through tooltip.
- [ ] Run the targeted tests and confirm they fail.
- [ ] Update `_set_connection_state()` to render a colored circular indicator for idle, connecting, connected, and failed states.
- [ ] Run the targeted tests and confirm they pass.

### Task 4: Saved Password Autofill

**Files:**
- Modify: `src/filezall_desktop/controller.py`
- Modify: `src/filezall_desktop/main_window.py`
- Test: `tests/desktop/test_controller.py`
- Test: `tests/desktop/test_main_window.py`

- [ ] Write failing tests showing saved site profiles and stored credentials populate the visible connection fields after startup/load.
- [ ] Run the targeted tests and confirm they fail.
- [ ] Let `load_saved_sites()` pass a credential lookup callback to the window, and let `MainWindow` select the first saved site and populate host, username, port, protocol, paths, auth mode, SSH key, and secret.
- [ ] Run the targeted tests and confirm they pass.

### Task 5: Verification, Merge, and Repackage

**Files:**
- Modify generated packaging output under `dist/`

- [ ] Run desktop and controller tests.
- [ ] Run the full pytest suite.
- [ ] Launch the desktop app smoke test.
- [ ] Merge the feature branch to `master`.
- [ ] Push `master` to GitHub.
- [ ] Rebuild the Windows portable package.
- [ ] Launch the packaged executable smoke test.
