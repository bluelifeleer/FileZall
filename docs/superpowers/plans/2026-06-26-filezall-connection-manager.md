# FileZall Connection Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Site Manager window for grouped, searchable, editable, duplicable, deletable, importable, and exportable saved connections.

**Architecture:** Keep persistence in `SiteRepository`; add import/export helpers in core and a desktop dialog in `src/filezall_desktop/site_manager.py`. `MainWindow` only opens the dialog and refreshes the existing site selector after changes.

**Tech Stack:** Python 3.12, PySide6, SQLite, JSON import/export, pytest, pytest-qt.

---

### Task 1: Site Groups In Storage

**Files:**
- Modify: `src/filezall_core/models.py`
- Modify: `src/filezall_core/storage.py`
- Modify: `src/filezall_core/site_repository.py`
- Test: `tests/core/test_site_repository.py`

- [x] **Step 1: Write failing repository test**

Add a test that saves a `SiteProfile` with `group_name="Production"` and verifies `SiteRepository.list()` returns the group.

- [x] **Step 2: Verify the test fails**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_site_repository.py::test_site_repository_persists_group_name -q`

Expected: fail because `group_name` does not exist.

- [x] **Step 3: Add group field and migration-safe column**

Add `group_name: str = ""` to `SiteProfile`. Add a storage migration that creates the `group_name` column when missing.

- [x] **Step 4: Verify repository tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_site_repository.py tests\core\test_storage.py -q`

Expected: pass.

### Task 2: Import And Export

**Files:**
- Create: `src/filezall_core/site_import_export.py`
- Test: `tests/core/test_site_import_export.py`

- [x] **Step 1: Write failing import/export tests**

Test that export writes site metadata without password values and import returns `SiteProfile` objects with credential references cleared.

- [x] **Step 2: Verify the tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_site_import_export.py -q`

Expected: fail because the module does not exist.

- [x] **Step 3: Implement JSON import/export**

Export `id`, `name`, `host`, `port`, `protocol`, `username`, `auth_mode`, `default_local_path`, `default_remote_path`, `ssh_key_path`, `agent_enabled`, `agent_token_ref`, and `group_name`. Do not export password or passphrase secrets.

- [x] **Step 4: Verify import/export tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_site_import_export.py -q`

Expected: pass.

### Task 3: Site Manager Dialog

**Files:**
- Create: `src/filezall_desktop/site_manager.py`
- Modify: `src/filezall_desktop/main_window.py`
- Modify: `src/filezall_desktop/i18n.py`
- Test: `tests/desktop/test_site_manager.py`
- Test: `tests/desktop/test_main_window.py`

- [x] **Step 1: Write failing UI tests**

Test that Tools or Session -> Site Manager opens a dialog with search, group filter, new, edit, duplicate, delete, import, export, and close controls.

- [x] **Step 2: Verify the tests fail**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_site_manager.py tests\desktop\test_main_window.py::test_main_window_opens_site_manager -q`

Expected: fail because `SiteManagerDialog` does not exist.

- [x] **Step 3: Implement read-only shell**

Create `SiteManagerDialog` that renders saved sites in a table and filters by search text and group.

- [x] **Step 4: Add edit actions**

Wire create/edit/duplicate/delete to `SiteRepository`. Delete must require confirmation. After accepted changes, emit `sites_changed`.

- [x] **Step 5: Add import/export actions**

Use `site_import_export.py`. After import, save imported sites and refresh the table. Export must show the credential-manager explanation and state that secrets are excluded.

- [x] **Step 6: Verify site manager tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\desktop\test_site_manager.py tests\desktop\test_main_window.py::test_main_window_opens_site_manager -q`

Expected: pass.

### Task 4: Integration And Commit

- [x] **Step 1: Run focused tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests\core\test_site_repository.py tests\core\test_site_import_export.py tests\desktop\test_site_manager.py tests\desktop\test_main_window.py`

Expected: pass.

- [x] **Step 2: Run full tests**

Run: `.\.venv\Scripts\python.exe -m pytest`

Expected: pass, with live SFTP skipped when environment variables are absent.

- [x] **Step 3: Commit**

Run:

```powershell
git add src tests docs
git commit -m "Add site manager"
```
