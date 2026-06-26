# FileZall UX Productization Roadmap

## Goal

Move FileZall from a capable transfer tool toward a polished commercial desktop product by making first use, connection setup, transfer progress, Agent management, diagnostics, and visual feedback clear and predictable.

## Product Principles

- Keep Quick Connect lightweight; move advanced setup into dedicated flows.
- Reuse existing transfer, site, credential, Agent, and logging services instead of duplicating behavior in dialogs.
- Every long-running operation must show an active state, step progress, success, failure, and a next action.
- Every destructive operation must have confirmation or a reversible path.
- Every user-visible string added in this roadmap must have English and Simplified Chinese coverage.
- Every milestone must land with tests and a small commit.

## Scope

This design is a multi-step UX roadmap. Each milestone must ship as a working, testable slice:

1. First-use guided workflow.
2. Connection manager.
3. File operation experience.
4. Transfer center.
5. Agent and resource monitoring experience.
6. Logs and diagnostics.
7. Visual polish and usability details.

The first implementation slice already added the Help -> Getting Started guide. The next first-use milestone extends that guide into a launch-time workflow with connection testing and clear failure messages.

## Milestone 1: First-Use Guided Workflow

The guide must help a new user complete the first useful workflow:

1. Create or choose a connection.
2. Enter server credentials.
3. Test the connection.
4. Connect and load the remote home directory.
5. Choose a local directory.
6. Enter or browse a remote directory.
7. Optionally install or update the Agent.
8. Upload, download, or add files to the queue.

Connection failures must be classified into user-facing causes: bad password, unreachable host or port, authentication failure, permission denied, missing Agent, systemd unsupported, Agent unhealthy, and unknown failure. The guide must let users save the successful setup as a site so the next launch can connect from the site selector.

## Milestone 2: Connection Manager

Add a dedicated Site Manager window with groups, search, create, edit, duplicate, delete, import, and export. The top Quick Connect bar remains for fast one-off connections. Saved-password copy must clearly state that secrets are stored through the operating system credential store and are not written to plain configuration files.

## Milestone 3: File Operation Experience

Make local and remote file operations feel complete and symmetric. The lists must support refresh, rename, delete, create directory, create file, copy path, upload, download, add to queue, drag upload/download, conflict policy prompts, and recursive directory transfer progress with total file count, total bytes, current item, and aggregate progress.

## Milestone 4: Transfer Center

Upgrade the transfer area into a clearer transfer center with speed, remaining time, retry count, failure reason, pause, resume, cancel, retry, concurrency, and limit controls. The queue should remain the source of truth.

The transfer center must show weak network and reconnect states clearly. Users should see when a task is waiting, running, paused, retrying, failed, or completed.

## Milestone 5: Agent And Resource Monitoring Experience

Replace binary Agent feedback with a state card: not installed, installing, installed, version outdated, unhealthy, update available, uninstalling, and unavailable. Agent install must show step progress in a visible panel, not only logs. Resource monitoring must add time range controls, hover details, network curves, disk partition views, and process sorting/filtering.

## Milestone 6: Logs And Diagnostics

The product should make support possible without asking users to reproduce manually. Logs must be categorized, sensitive fields redacted, and diagnostics export should include runtime logs, transfer logs, app settings metadata, and Agent status context.

Log categories are connection, transfer, Agent, resource, and error. Error rows must support copy and diagnostics export.

## Milestone 7: Visual Polish And Usability Details

Use consistent action colors:

- Primary: connect, upload, download.
- Neutral: refresh, choose directory, copy path.
- Warning: pause, retry, Agent update.
- Danger: delete, uninstall Agent.

Add high-quality file icons, list density options, theme continuation, and keyboard shortcuts:

- Ctrl+A selects all rows.
- F5 refreshes active panel.
- Delete deletes selected rows after confirmation.
- Enter enters a selected directory.
- Backspace moves to the parent directory.

All critical dialogs, menu labels, status messages, and log categories must have English and Simplified Chinese translations.

## Execution Documents

- `docs/superpowers/plans/2026-06-26-filezall-first-use-workflow.md`
- `docs/superpowers/plans/2026-06-26-filezall-connection-manager.md`
- `docs/superpowers/plans/2026-06-26-filezall-file-operations-experience.md`
- `docs/superpowers/plans/2026-06-26-filezall-transfer-center.md`
- `docs/superpowers/plans/2026-06-26-filezall-agent-resource-experience.md`
- `docs/superpowers/plans/2026-06-26-filezall-logs-diagnostics-experience.md`
- `docs/superpowers/plans/2026-06-26-filezall-visual-usability-polish.md`

## Testing Strategy

Every milestone needs PySide6 UI tests for visible controls and controller tests for behavior. Longer-running transfer and Agent flows use core service tests plus focused desktop tests. Packaging smoke should run after UI-affecting milestones.
