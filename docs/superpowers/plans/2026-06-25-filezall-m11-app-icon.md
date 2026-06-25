# FileZall M11 App Icon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a FileZall application icon that appears in the running desktop app, packaged executable, installer metadata, shortcuts, and macOS app bundle.

**Architecture:** Store source and platform icon assets under `src/filezall_desktop/assets/icons`. The desktop app loads the icon through a small helper, while PyInstaller and Inno Setup reference the same assets during packaging.

**Tech Stack:** PySide6 `QIcon`, PyInstaller `EXE(icon=...)` and `BUNDLE(icon=...)`, Inno Setup `SetupIconFile`, pytest.

---

## Task 1: Icon Assets And Packaging Contracts

- [ ] Add failing tests for required icon files and packaging references.
- [ ] Generate `filezall.svg`, `filezall.ico`, and `filezall.icns`.
- [ ] Update PyInstaller spec and Inno Setup script to reference the icon.
- [ ] Run packaging tests and commit.

## Task 2: Runtime Window Icon

- [ ] Add failing desktop test that `MainWindow` has a non-null window icon.
- [ ] Add icon loading helper and set the window icon.
- [ ] Run desktop tests and commit.

## Task 3: Verification

- [ ] Run full tests.
- [ ] Run Windows packaging build.
- [ ] Launch packaged executable smoke test.
- [ ] Merge to `master` and push.
