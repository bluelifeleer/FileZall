# FileZall First-Use Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a lightweight Getting Started guide that explains the first successful FileZall workflow and focuses existing controls.

**Architecture:** Add a small `GettingStartedDialog` widget that owns only guide presentation. `MainWindow` owns menu wiring and focus actions because it already owns the connection bar and file panels. Translation strings live in the existing `i18n.py` dictionaries.

**Tech Stack:** Python 3.12, PySide6, pytest-qt, existing FileZall desktop widgets.

---

### Task 1: Add Getting Started Dialog

**Files:**
- Create: `src/filezall_desktop/onboarding.py`
- Modify: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write the failing dialog test**

Add a test that opens the Help menu action, verifies the guide is created, verifies it contains six steps, and verifies the primary action focuses the host field.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_getting_started_guide_opens_from_help_menu -q`

Expected: fail because the menu action does not exist.

- [ ] **Step 3: Implement the dialog**

Create `GettingStartedDialog` with six visible step labels and three action buttons:

- Focus Connection
- Focus Local Files
- Focus Remote Files

The dialog emits `focus_connection_requested`, `focus_local_requested`, and `focus_remote_requested`.

- [ ] **Step 4: Wire it into MainWindow**

Add Help -> Getting Started. Opening the action creates and shows one dialog. Connect dialog signals to focus existing controls:

- connection: host field
- local: local path field
- remote: remote path field

- [ ] **Step 5: Run targeted tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_getting_started_guide_opens_from_help_menu -q`

Expected: pass.

### Task 2: Add Translations

**Files:**
- Modify: `src/filezall_desktop/i18n.py`
- Modify: `tests/desktop/test_main_window.py`

- [ ] **Step 1: Write the failing translation test**

Add assertions that English and Chinese language actions update Help -> Getting Started and the dialog title.

- [ ] **Step 2: Run the test to verify it fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_getting_started_guide_follows_language -q`

Expected: fail because translations are not wired.

- [ ] **Step 3: Add translation keys**

Add keys for menu action, dialog title, dialog intro, six step labels, and three action buttons.

- [ ] **Step 4: Refresh dialog text on language change**

When language changes, update the menu action text. The dialog should be built from the active language when opened.

- [ ] **Step 5: Run targeted tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py::test_getting_started_guide_follows_language -q`

Expected: pass.

### Task 3: Verify and Commit

**Files:**
- Verify all files changed by Tasks 1 and 2.

- [ ] **Step 1: Run desktop tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py tests\desktop\test_app_bootstrap.py`

Expected: pass.

- [ ] **Step 2: Run full tests**

Run: `.\.venv\Scripts\python.exe -m pytest`

Expected: pass, with live SFTP skipped when environment variables are absent.

- [ ] **Step 3: Commit**

Run:

```powershell
git add docs/superpowers/specs/2026-06-26-filezall-ux-productization-design.md docs/superpowers/plans/2026-06-26-filezall-first-use-guide.md src/filezall_desktop/onboarding.py src/filezall_desktop/main_window.py src/filezall_desktop/i18n.py tests/desktop/test_main_window.py
git commit -m "Add getting started guide"
```

