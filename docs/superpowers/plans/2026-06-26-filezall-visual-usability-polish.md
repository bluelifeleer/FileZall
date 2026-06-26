# FileZall Visual And Usability Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the desktop UI visually consistent and faster to operate with button roles, better file icons, density controls, shortcuts, confirmations, and complete translations.

**Architecture:** Centralize visual roles in the existing theme module and keep widgets role-aware through object names or dynamic properties. Add file icon mapping in one helper. Add shortcuts at `MainWindow` level and delegate active-panel actions to existing handlers.

**Tech Stack:** Python 3.12, PySide6, pytest-qt, existing theme and i18n modules.

---

### Task 1: Button Role System

**Files:**
- Modify: `src/filezall_desktop/theme.py`
- Modify: `src/filezall_desktop/main_window.py`
- Test: `tests/desktop/test_main_window.py`

- [x] **Step 1: Write failing role tests**

Test primary, neutral, warning, danger, loading, and disabled visual roles are assigned to the expected buttons.

- [x] **Step 2: Verify tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_buttons_use_consistent_visual_roles -q`

Expected: fail because not all roles are assigned.

- [x] **Step 3: Extend stylesheet**

Add role selectors for `primary`, `neutral`, `warning`, `danger`, `loading`, and disabled states.

- [x] **Step 4: Assign roles**

Assign connect/upload/download as primary; refresh/path/copy as neutral; pause/retry/update as warning; delete/uninstall as danger.

- [x] **Step 5: Verify role tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_buttons_use_consistent_visual_roles -q`

Expected: pass.

### Task 2: File Icon Quality

**Files:**
- Modify: `src/filezall_desktop/widgets.py`
- Create or modify: `src/filezall_desktop/assets/icons/`
- Test: `tests/desktop/test_main_window.py`

- [x] **Step 1: Write failing icon tests**

Test directories use one directory icon and files use extension-based icons for py, txt, zip, image, config, and unknown files.

- [x] **Step 2: Verify tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_file_list_uses_extension_icons -q`

Expected: fail because extension mapping is incomplete.

- [x] **Step 3: Add icon helper**

Create one helper that maps extension groups to icons and returns a fallback icon for unknown file types.

- [x] **Step 4: Verify icon tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_file_list_uses_extension_icons -q`

Expected: pass.

### Task 3: List Density

**Files:**
- Modify: `src/filezall_desktop/widgets.py`
- Modify: `src/filezall_desktop/main_window.py`
- Modify: `src/filezall_desktop/i18n.py`
- Test: `tests/desktop/test_main_window.py`

- [x] **Step 1: Write failing density tests**

Test compact, standard, and comfortable density actions update row heights and remain stable after refresh.

- [x] **Step 2: Verify tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_file_list_density_actions_update_row_height -q`

Expected: fail because density controls do not exist.

- [x] **Step 3: Add density actions**

Add View or Theme menu density actions. Store active density in `MainWindow`.

- [x] **Step 4: Apply density**

Set table vertical header default section size for both file panels.

- [x] **Step 5: Verify density tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_file_list_density_actions_update_row_height -q`

Expected: pass.

### Task 4: Shortcuts And Confirmations

**Files:**
- Modify: `src/filezall_desktop/main_window.py`
- Modify: `src/filezall_desktop/i18n.py`
- Test: `tests/desktop/test_main_window.py`

- [x] **Step 1: Write failing shortcut tests**

Test Ctrl+A selects active panel rows, F5 refreshes active panel, Delete prompts delete, Enter enters selected directory, and Backspace navigates to parent.

- [x] **Step 2: Verify tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_file_panel_keyboard_shortcuts -q`

Expected: fail because shortcuts are not fully wired.

- [x] **Step 3: Add shortcuts**

Add `QShortcut` instances in `MainWindow`. Track active panel by focus and mouse entry.

- [x] **Step 4: Add confirmations**

Add delete and Agent uninstall confirmations with action-specific text.

- [x] **Step 5: Verify shortcut tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_file_panel_keyboard_shortcuts tests\desktop\test_main_window.py::test_delete_requires_confirmation -q`

Expected: pass.

### Task 5: Translation Coverage

**Files:**
- Modify: `src/filezall_desktop/i18n.py`
- Test: `tests/desktop/test_main_window.py`

- [x] **Step 1: Write failing coverage test**

Test that every English translation key exists in Simplified Chinese and no visible menu/action text added by this roadmap falls back to raw keys.

- [x] **Step 2: Verify test fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_translation_keys_are_complete -q`

Expected: fail if keys are missing.

- [x] **Step 3: Fill translations**

Add missing English and Simplified Chinese strings for menus, dialogs, status messages, log categories, shortcut labels, and confirmations.

- [x] **Step 4: Verify translation tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_translation_keys_are_complete -q`

Expected: pass.

### Task 6: Commit

- [x] **Step 1: Run focused tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py`

Expected: pass.

- [x] **Step 2: Run full tests**

Run: `.\.venv\Scripts\python.exe -m pytest`

Expected: pass, with live SFTP skipped when environment variables are absent.

- [x] **Step 3: Package smoke**

Run: `powershell -ExecutionPolicy Bypass -File packaging\windows\release.ps1`

Expected: Windows portable zip and setup exe are generated.

- [x] **Step 4: Commit**

Run:

```powershell
git add src tests docs
git commit -m "Polish visual usability"
```
