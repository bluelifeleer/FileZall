# FileZall M10 Release Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Windows packaging executable on this machine and add a repeatable real Linux Agent end-to-end validation script.

**Architecture:** Keep packaging orchestration in platform scripts and keep tests at the script/metadata contract level. Real external verification is opt-in through environment variables so normal tests stay deterministic.

**Tech Stack:** PowerShell, PyInstaller, optional Inno Setup, OpenSSH `ssh`/`scp`, pytest.

---

## Task 1: Windows Build Script Hardening

**Files:**
- Modify: `packaging/windows/build.ps1`
- Modify: `packaging/windows/FileZall.iss`
- Modify: `tests/test_packaging_files.py`

- [ ] Write tests asserting the Windows build script uses `.venv`, `python -m PyInstaller`, and that Inno `AppId` is a valid GUID-style value.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests/test_packaging_files.py -v` and verify the new assertions fail.
- [ ] Update the Windows build script and Inno metadata.
- [ ] Re-run `.\.venv\Scripts\python.exe -m pytest tests/test_packaging_files.py -v`.
- [ ] Commit with `build: harden Windows packaging script`.

## Task 2: Linux Agent Real-Server Validation Script

**Files:**
- Create: `scripts/validate-linux-agent.ps1`
- Modify: `tests/test_packaging_files.py`
- Modify: `docs/agent-deployment.md`

- [ ] Write tests asserting the validation script exists and contains required environment names, `scp`, `ssh -L`, `systemctl`, `/health`, and `/resources`.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests/test_packaging_files.py -v` and verify the new assertions fail.
- [ ] Add the validation script and link it from Agent deployment docs.
- [ ] Re-run `.\.venv\Scripts\python.exe -m pytest tests/test_packaging_files.py -v`.
- [ ] Commit with `test: add Linux Agent validation script`.

## Task 3: Real Windows Build Verification

- [ ] Ensure PyInstaller is installed in `.venv`; if missing, install it with pip.
- [ ] Run `powershell -ExecutionPolicy Bypass -File packaging/windows/build.ps1`.
- [ ] Verify `dist\FileZall\FileZall.exe` exists.
- [ ] Run the built executable with a short smoke launch when possible, or document if GUI launch cannot be automated from the packaged app.

## Task 4: Full Verification And Merge

- [ ] Run `.\.venv\Scripts\python.exe -m pytest -v`.
- [ ] Run GUI source smoke test.
- [ ] If Linux server environment variables are present, run `scripts/validate-linux-agent.ps1`; otherwise report that real host credentials are required.
- [ ] Merge to `master` and push.

## Self-Review

- Spec coverage: Windows real build path and Linux real-server verification entry point are both covered.
- Placeholder scan: No placeholders are used.
- Type consistency: Script names and environment variables match the design document.
