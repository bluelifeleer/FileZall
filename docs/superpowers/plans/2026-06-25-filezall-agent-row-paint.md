# FileZall Agent and Row Paint Fix Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix broken-looking selected/hovered file rows, restore compact directory chooser text, and add visible Agent install/uninstall workflow feedback.

**Architecture:** Keep row activity rendering inside `HoverRowTableWidget` and its delegate. Keep Agent actions in `MainWindowController`; `MainWindow` owns confirmation and logs. Extend the existing Agent install service seam with an optional `uninstall()` method.

**Tech Stack:** Python, PySide6, pytest-qt.

---

### Task 1: Regression Tests

- [ ] Add tests that selected and hovered rows use full-row table painting without per-cell focus/selection decorations.
- [ ] Add tests that local directory chooser keeps compact `...` text after language refresh.
- [ ] Add tests that Agent install logs start/confirm/done messages.
- [ ] Add tests that an uninstall Agent button exists and calls controller uninstall with logs.

### Task 2: Row Paint Fix

- [ ] Change `HoverRowDelegate.paint()` to paint active row backgrounds itself and draw text without focus/selection state.
- [ ] Keep table trailing area painting for full-width rows.
- [ ] Ensure stylesheet no longer paints item hover/selection fragments.

### Task 3: Agent Install and Uninstall Feedback

- [ ] Add `uninstall_agent()` to controller.
- [ ] Add uninstall button beside install button.
- [ ] Append logs before and after install/uninstall actions.
- [ ] Disable Agent action buttons while an action runs.

### Task 4: Verify and Package

- [ ] Run targeted tests.
- [ ] Run full `pytest`.
- [ ] Build Windows portable app and Inno installer.
- [ ] Smoke launch packaged executable.
