# FileZall Navigation and I18n Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix broken-looking table row activity, make local directory navigation work at every depth, add remote loading feedback, and add system-following language selection.

**Architecture:** Keep the existing PySide6 desktop structure. `HoverRowTableWidget` owns continuous row background painting. `MainWindow` owns language/theme menus and UI text refresh. `MainWindowController` updates the local path field after local directory loads.

**Tech Stack:** Python, PySide6, pytest-qt.

---

### Task 1: Regression Tests

**Files:**
- Modify: `tests/desktop/test_main_window.py`
- Modify: `tests/desktop/test_controller.py`

- [ ] Write failing tests for continuous row activity flags, deep local path synchronization, remote loading status, and Language menu behavior.
- [ ] Run the targeted tests and confirm they fail for the expected missing behavior.

### Task 2: Continuous Row Activity

**Files:**
- Modify: `src/filezall_desktop/widgets.py`
- Modify: `src/filezall_desktop/theme.py`

- [ ] Disable grid rendering for file tables.
- [ ] Paint hover and selected row backgrounds across the full viewport width.
- [ ] Make delegate cells transparent for active rows so column boundaries no longer break the row activity state.

### Task 3: Directory Loading Behavior

**Files:**
- Modify: `src/filezall_desktop/controller.py`
- Modify: `src/filezall_desktop/main_window.py`

- [ ] Add a `set_local_directory_path(path)` method on `MainWindow`.
- [ ] Have `MainWindowController.load_local_directory()` update the local path field after a successful load.
- [ ] Add remote loading status helpers and use them around all remote directory navigation entry points.

### Task 4: Language Selection

**Files:**
- Create: `src/filezall_desktop/i18n.py`
- Modify: `src/filezall_desktop/main_window.py`
- Modify: `src/filezall_desktop/widgets.py`

- [ ] Add System, English, and Simplified Chinese labels.
- [ ] Add a Language menu and default to System.
- [ ] Refresh common UI labels, buttons, table headers, context menu labels, resource labels, and menu labels when language changes.

### Task 5: Verification and Packaging

**Files:**
- No source changes expected.

- [ ] Run `.\.venv\Scripts\python.exe -m pytest`.
- [ ] Rebuild Windows artifacts.
- [ ] Smoke launch `dist\FileZall\FileZall.exe`.
- [ ] Record installer and portable zip SHA256 hashes.
