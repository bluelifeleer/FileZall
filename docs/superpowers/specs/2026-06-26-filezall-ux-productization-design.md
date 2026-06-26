# FileZall UX Productization Design

## Goal

Move FileZall from a capable transfer tool toward a polished commercial desktop product by making first use, connection setup, transfer progress, Agent management, diagnostics, and visual feedback clear and predictable.

## Scope

This design is a multi-step UX roadmap. Each milestone must ship as a working, testable slice:

1. First-use guide.
2. Connection manager.
3. Transfer center.
4. File conflict and recursive directory progress.
5. Agent status center.
6. Logs and diagnostics polish.
7. Visual consistency polish.

The first implementation slice is the first-use guide. Later slices get their own detailed implementation plans before code changes.

## First-Use Guide

Add a lightweight guided dialog available from the Help menu as "Getting Started". It gives a new user a clear sequence:

1. Create or choose a connection.
2. Enter server credentials.
3. Connect and load the remote home directory.
4. Optionally install or update the Agent.
5. Select local and remote folders.
6. Upload, download, or add files to the queue.

The guide must not block experienced users. It is informational and action-oriented, with buttons that focus existing UI controls instead of duplicating connection logic.

## Connection Manager

Add a dedicated site management window after the first-use guide lands. It should support list, search, create, edit, duplicate, delete, import, and export. Quick Connect remains in the top bar for fast access. Advanced configuration belongs in the manager.

## Transfer Center

Upgrade the transfer area into a clearer transfer center with speed, remaining time, retry count, failure reason, pause, resume, cancel, retry, concurrency, and limit controls. The queue should remain the source of truth.

## File Operations

Keep local and remote file operations symmetrical where possible: refresh, rename, delete, create directory, create file, copy path, upload, download, add to queue, and later move/copy/permissions. Directory transfers need recursive progress with total count, total bytes, current item, and aggregate progress.

## Agent Experience

Replace binary Agent feedback with states: unknown, not installed, installing, installed, update available, unhealthy, uninstalling. Agent actions should show step progress and clear failure guidance.

## Diagnostics

The product should make support possible without asking users to reproduce manually. Logs must be categorized, sensitive fields redacted, and diagnostics export should include runtime logs, transfer logs, app settings metadata, and Agent status context.

## Visual System

Use consistent action colors:

- Primary: connect, upload, download.
- Neutral: refresh, choose directory, copy path.
- Warning: pause, retry, Agent update.
- Danger: delete, uninstall Agent.

Add high-quality file icons, density options, and complete theme/language coverage across menus, dialogs, status text, and logs.

## Testing Strategy

Every milestone needs PySide6 UI tests for visible controls and controller tests for behavior. Longer-running transfer and Agent flows use core service tests plus focused desktop tests. Packaging smoke should run after UI-affecting milestones.

