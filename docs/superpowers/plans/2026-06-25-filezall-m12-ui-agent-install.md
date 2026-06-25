# FileZall M12 UI Agent Install Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve file-panel navigation, add Help/About information, make major UI regions resizable, and add a user-confirmed Agent install action after connecting to a server.

**Architecture:** Keep UI behavior in `MainWindow` and reusable panel affordances in `widgets.py`. Keep Agent installation orchestration behind injectable controller dependencies so tests can exercise the button flow without a real server.

**Tech Stack:** PySide6, pytest-qt, existing `AgentInstaller`, existing desktop controller.

---

## Task 1: Compact Directory Controls And Refresh Selection Clearing

- [ ] Add failing desktop tests for compact path tool buttons, local directory selection, remote selected-directory entry, and refresh clearing table selection.
- [ ] Implement `FilePanel.path_button` as a compact `QToolButton`.
- [ ] Implement local directory chooser injection and remote directory entry behavior.
- [ ] Clear selection before refresh actions.
- [ ] Run desktop tests and commit.

## Task 2: Draggable Main Regions

- [ ] Add failing desktop tests that verify horizontal file splitter and vertical main splitter exist.
- [ ] Convert the central layout to a vertical splitter containing file panels, transfer center, and resource monitor.
- [ ] Run desktop tests and commit.

## Task 3: Help Menu

- [ ] Add failing desktop tests for Help menu actions: About, Version, Protocols.
- [ ] Add menu actions with status tips and message dialogs.
- [ ] Run desktop tests and commit.

## Task 4: Install Agent Button

- [ ] Add failing controller/UI tests for a post-connect Install Agent action that asks confirmation and invokes an injected installer.
- [ ] Add compact `Install Agent` toolbar action.
- [ ] Add controller method `install_agent()` with clear status results.
- [ ] Run controller/desktop tests and commit.

## Task 5: Full Verification

- [ ] Run full pytest.
- [ ] Run GUI smoke test.
- [ ] Run Windows packaging build smoke if time permits.
- [ ] Merge to `master` and push.
