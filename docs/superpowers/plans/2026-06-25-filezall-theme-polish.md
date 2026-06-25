# FileZall Theme Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the desktop UI feel more polished with selectable themes and one coordinated full-row hover state.

**Architecture:** Add a small theme module that produces app-wide Qt stylesheets. `MainWindow` exposes a Theme menu and applies the selected stylesheet. `HoverRowTableWidget` and its delegate continue to own row-hover rendering.

**Tech Stack:** Python, PySide6, pytest-qt.

---

### Task 1: Theme Menu Tests

**Files:**
- Modify: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write the failing tests**

Add tests that assert a Theme menu exists with System, Light, and Dark actions, and that triggering Light/Dark changes `window.styleSheet()`.

- [ ] **Step 2: Run the tests to verify failure**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_main_window_has_theme_menu_actions tests\desktop\test_main_window.py::test_main_window_applies_theme_actions -v`

Expected: fail because the Theme menu does not exist yet.

### Task 2: Theme Implementation

**Files:**
- Create: `src/filezall_desktop/theme.py`
- Modify: `src/filezall_desktop/main_window.py`

- [ ] **Step 1: Implement theme helpers**

Create theme constants for `system`, `light`, and `dark`, a system preference resolver, and a `stylesheet_for_theme(theme_name)` function.

- [ ] **Step 2: Wire the MainWindow menu**

Add a Theme menu with checkable System, Light, and Dark actions. Triggering an action sets `self.current_theme` and applies the stylesheet.

- [ ] **Step 3: Run the theme tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_main_window_has_theme_menu_actions tests\desktop\test_main_window.py::test_main_window_applies_theme_actions -v`

Expected: pass.

### Task 3: Full-Row Hover Polish

**Files:**
- Modify: `src/filezall_desktop/widgets.py`
- Modify: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write the failing hover test**

Assert `HoverRowTableWidget.full_row_hover_color` exists and the table tracks hover rows.

- [ ] **Step 2: Update hover painting**

Have the table fill the hovered row across the full viewport width, and let the delegate use the same hover color for cell painting.

- [ ] **Step 3: Run the desktop tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py -v`

Expected: pass.

### Task 4: Verification and Packaging

**Files:**
- No source changes expected.

- [ ] **Step 1: Run full tests**

Run: `.\.venv\Scripts\python.exe -m pytest`

Expected: all tests pass, except live SFTP may skip when credentials are not configured.

- [ ] **Step 2: Build Windows artifacts**

Run: `$env:Path = "$env:LOCALAPPDATA\Programs\Inno Setup 6;$env:Path"; powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1`

Expected: `dist\installer\FileZallSetup.exe` exists.

- [ ] **Step 3: Smoke packaged app**

Run the packaged `dist\FileZall\FileZall.exe` with `FILEZALL_HOME` pointed at `.filezall-smoke-package`, wait five seconds, and stop it if still running.

Expected: the process starts without a non-zero exit.
