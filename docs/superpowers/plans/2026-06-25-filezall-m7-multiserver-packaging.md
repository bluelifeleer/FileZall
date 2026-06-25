# FileZall M7 Multi-Server and Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-server session management foundations and Windows/macOS distribution packaging scaffolding.

**Architecture:** Multi-server state lives in `filezall_core.session_manager` so UI code can later render tabs or trees without owning connection lifecycle. Packaging is represented by checked-in PyInstaller, Windows installer, macOS bundle, and release documentation files that can be run in a build machine with platform tools installed.

**Tech Stack:** Python 3.12, pytest, PySide6, PyInstaller spec format, PowerShell build script for Windows, shell build script for macOS, Inno Setup script.

---

## Scope

This plan implements the M7 foundations from `docs/superpowers/specs/2026-06-24-filezall-design.md`:

- Multiple simultaneous connection/session management.
- Global transfer view already exists from M3; this plan adds per-server filtering helpers.
- Windows installer scaffold.
- macOS app/dmg scaffold.
- Basic release documentation.

This plan does not perform code signing, notarization, actual installer execution, or publish artifacts because those require external platform tools and certificates.

## File Structure

- Create: `src/filezall_core/session_manager.py`.
- Modify: `src/filezall_core/queue.py` - add per-server item listing helper.
- Create: `tests/core/test_session_manager.py`.
- Modify: `tests/core/test_queue.py`.
- Create: `packaging/filezall.spec`.
- Create: `packaging/windows/build.ps1`.
- Create: `packaging/windows/FileZall.iss`.
- Create: `packaging/macos/build.sh`.
- Create: `packaging/README.md`.
- Create: `tests/test_packaging_files.py`.

## Task 1: Multi-Server Session Manager

**Files:**
- Create: `src/filezall_core/session_manager.py`
- Test: `tests/core/test_session_manager.py`

- [ ] **Step 1: Write failing session-manager tests**

Create tests that use fake sessions and assert the manager can connect two sites, track the active site, switch active site, list sessions, and disconnect one site without closing the other.

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_session_manager.py -v
```

Expected: `ModuleNotFoundError: No module named 'filezall_core.session_manager'`.

- [ ] **Step 3: Implement session manager**

Create `SessionManager(session_factory)` with `connect(site, password=None)`, `get(site_id)`, `active()`, `switch(site_id)`, `list_site_ids()`, `disconnect(site_id)`, and `disconnect_all()`.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_session_manager.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/session_manager.py tests/core/test_session_manager.py
git commit -m "feat: add multi-server session manager"
```

## Task 2: Per-Server Transfer View Helper

**Files:**
- Modify: `src/filezall_core/queue.py`
- Modify: `tests/core/test_queue.py`

- [ ] **Step 1: Write failing queue filtering test**

Add a test that creates transfer items for two server IDs and asserts `TransferQueue.list_items(server_id="site-1")` returns only that server's rows.

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_queue.py -v
```

Expected: `TypeError` because `list_items()` has no `server_id` argument.

- [ ] **Step 3: Implement per-server filter**

Update `TransferQueue.list_items(status=None, server_id=None)` to filter returned rows by server ID after repository query.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_queue.py -v
```

Expected: all queue tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/queue.py tests/core/test_queue.py
git commit -m "feat: add per-server transfer view helper"
```

## Task 3: Packaging Scaffolding

**Files:**
- Create: `packaging/filezall.spec`
- Create: `packaging/windows/build.ps1`
- Create: `packaging/windows/FileZall.iss`
- Create: `packaging/macos/build.sh`
- Create: `packaging/README.md`
- Test: `tests/test_packaging_files.py`

- [ ] **Step 1: Write failing packaging-file tests**

Create tests that assert the packaging files exist and contain expected commands: `pyinstaller`, `filezall_desktop.app`, `Inno Setup`, `create-dmg`, and platform notes for signing/notarization.

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_packaging_files.py -v
```

Expected: file existence assertions fail.

- [ ] **Step 3: Add packaging files**

Add PyInstaller spec, Windows PowerShell build wrapper, Inno Setup script, macOS build wrapper, and packaging README. Scripts should fail fast with clear messages if required platform tools are missing.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_packaging_files.py -v
```

Expected: all packaging-file tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add packaging tests/test_packaging_files.py
git commit -m "build: add desktop packaging scaffolding"
```

## Task 4: Full M7 Verification

- [ ] **Step 1: Run all tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Expected: all non-live tests pass; optional live SFTP test is skipped unless configured.

- [ ] **Step 2: Run GUI smoke test**

Run:

```powershell
$env:FILEZALL_HOME = (Join-Path (Get-Location) '.filezall-smoke'); .\.venv\Scripts\python.exe -c "from PySide6.QtCore import QTimer; from PySide6.QtWidgets import QApplication; from filezall_desktop.app import create_main_window; app = QApplication([]); window = create_main_window(); window.show(); QTimer.singleShot(100, app.quit); raise SystemExit(app.exec())"
```

Expected: exit code 0.

- [ ] **Step 3: Check working tree**

Run:

```powershell
git status --short
```

Expected: no output.

## Self-Review

- Spec coverage: Multi-server session management, per-server transfer filtering, and Windows/macOS packaging scaffolds are covered.
- Out of scope: Real signing, notarization, installer execution, and UI tabs are deferred to release engineering work after functional milestones.
- Placeholder scan: No placeholders; tasks name concrete files and expected verification.
- Type consistency: Session manager uses existing `SiteProfile` and `RemoteSession`-like objects; queue helper uses existing `TransferItem.server_id`.
