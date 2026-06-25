# FileZall M13 File Ops Status Logs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add file-list navigation and context actions, connection status feedback, credential-save choice, transfer logs with export, and Agent-not-installed resource UI.

**Architecture:** Keep reusable table/menu affordances in `FilePanel`, route user commands through `MainWindow`, and keep durable behavior in `MainWindowController`. Add a small core log service so UI logs can be displayed and exported without coupling to Qt.

**Tech Stack:** PySide6, pytest-qt, Python core services, existing credential/site/Agent services.

---

## Task 1: File Panel Navigation And Context Menus

- [ ] Add tests for double-click directory entry, path edit Enter navigation, and context menu actions.
- [ ] Implement `FilePanel` signals/actions for refresh, delete, queue, upload/download, create directory, and create file.
- [ ] Route local/remote actions through `MainWindow`.
- [ ] Run desktop tests and commit.

## Task 2: Connection Loading And Status Light

- [ ] Add tests for connecting state and status light colors.
- [ ] Add status light widget on the right side of the status bar.
- [ ] Set yellow while connecting, green on success, red on failure, grey when idle.
- [ ] Run controller/desktop tests and commit.

## Task 3: Remember Password Choice

- [ ] Add tests for "remember password" and "do not remember" flows.
- [ ] Add confirmation callback in `MainWindow` and `remember_secret` flag in controller.
- [ ] Save credentials only when requested.
- [ ] Run controller/desktop tests and commit.

## Task 4: Transfer Logs And Export

- [ ] Add core log service tests.
- [ ] Add log panel to UI and `Logs -> Export Logs` action.
- [ ] Record connect, refresh, upload, download, queue, and Agent install events.
- [ ] Run tests and commit.

## Task 5: Agent Not Installed Resource UI

- [ ] Add tests for Agent-not-installed label and install button in Resource Monitor.
- [ ] Show install affordance when Agent is disabled/unavailable.
- [ ] Wire install button to existing confirmed Agent install action.
- [ ] Run tests and commit.

## Task 6: Full Verification

- [ ] Run full pytest.
- [ ] Run GUI smoke test.
- [ ] Merge to `master` and push.
