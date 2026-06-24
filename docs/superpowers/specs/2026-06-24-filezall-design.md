# FileZall Design Specification

## Goal

Build FileZall as a cross-platform desktop file transfer application for Windows and macOS. The product should feel like a more capable FileZilla: local and remote file browsing, multi-server connections, queued upload and download, resumable transfers, optional Linux Agent acceleration, and server resource monitoring.

## Confirmed Product Decisions

- Desktop client starts as PySide6 for fast delivery, with core modules kept independent so they can be migrated to C++ later.
- Architecture follows "PySide6 UI + independent Python core package + optional Linux Agent".
- Server-side first-class support is Linux.
- Client supports Windows and macOS installable distributions.
- Connection auth supports username/password and SSH Key.
- Transfer protocols include SFTP/SSH, FTP, FTPS, and enhanced HTTP transfer through FileZall Agent.
- Transfer resume supports both file-level resume and task-level resume.
- Credentials are saved in the OS credential store: Windows Credential Manager and macOS Keychain.
- Multiple servers can be connected at the same time.
- Queues use a hybrid model: per-server queues plus global concurrency limits and a global transfer view.

## System Architecture

FileZall is split into four major parts.

### Desktop App

The desktop app is the PySide6 user interface. It owns windows, menus, dialogs, file panels, queue views, server tabs, resource dashboards, process tables, and user interactions.

The UI must not directly implement protocol details. It calls the core engine through stable service interfaces and subscribes to progress/status events.

### Core Engine

The core engine is an independent Python package with no PySide6 dependency. It owns:

- Site configuration model.
- Connection lifecycle.
- Protocol adapter routing.
- Transfer task model.
- Queue scheduler.
- Resume state persistence.
- Retry and error handling.
- Transfer speed and concurrency limits.
- Local application database.

The core package is the main future migration candidate. Its public interface should stay narrow enough that the implementation can later move to C++ without rewriting the whole UI.

### Protocol Adapters

Each protocol is implemented behind a common file-operation interface:

- SFTP/SSH adapter.
- FTP adapter.
- FTPS adapter.
- Agent HTTP adapter.

The shared interface covers:

- Connect and disconnect.
- List directory.
- Stat file or directory.
- Upload file.
- Download file.
- Create directory.
- Delete file or directory.
- Rename or move.
- Query resume capability.

The UI and queue scheduler depend on this common interface rather than on protocol-specific APIs.

### FileZall Agent

FileZall Agent is an optional Linux service. It provides enhanced features:

- Health check.
- CPU, memory, disk, and network snapshots.
- Process list and process detail.
- HTTP chunked upload and download.
- Remote chunk status query.
- Final file merge and verification.

When Agent is unavailable, FileZall still supports file browsing and transfer through SFTP/FTP/FTPS. Resource monitoring is reduced or disabled depending on protocol capability.

## Desktop UX

The desktop UI uses a professional dual-pane file manager layout.

### Top Connection Area

The top area includes:

- Site selector.
- Host.
- Port.
- Protocol selector.
- Username.
- Auth mode.
- Connect and disconnect actions.
- Active server tabs or connection tree for multiple simultaneous servers.

### Local File Panel

The local panel supports:

- Choosing a local directory.
- Directory traversal.
- File list display.
- Refresh.
- Parent directory navigation.
- Sorting by name, size, type, and modified time.
- Search or filter.
- Upload selected local files or directories to the active remote directory.

First version should avoid heavy recursive live watching for very large directories. Directory content can load on navigation and refresh. Recursive enumeration is used when the user starts a directory transfer.

### Remote File Panel

The remote panel supports:

- Default entry into the authenticated user's home directory when supported.
- Manual remote path entry.
- Directory traversal.
- Refresh.
- Sorting.
- Upload target selection.
- Download selected files or directories.
- Create directory.
- Delete.
- Rename.

SFTP, FTP, FTPS, and Agent HTTP should share the same remote file UI.

### Transfer Center

The transfer center shows:

- Global queue view.
- Per-server queue view.
- Waiting tasks.
- Active transfers.
- Paused tasks.
- Failed tasks.
- Completed tasks.
- Progress.
- Speed.
- Estimated time remaining.
- Retry count.
- Resume status.

Actions include:

- Pause.
- Resume.
- Cancel.
- Retry.
- Remove completed tasks.

### Resource Monitor

The resource monitor shows:

- CPU usage.
- Memory total, used, and available.
- Disk partition usage.
- Network receive and send rate when available.
- Process table.
- Expandable process detail.

Process detail includes:

- PID.
- User.
- Process name.
- Command line.
- CPU percent.
- Memory percent.
- Start time.
- Thread count.
- Status.

For FTP/FTPS-only connections, the UI clearly indicates that resource monitoring requires SSH or Agent.

## Transfer Model

The queue model has two levels.

### TransferTask

A TransferTask represents a user-requested upload or download. It may be a single file or a directory.

Fields include:

- Task ID.
- Server ID.
- Direction: upload or download.
- Source path.
- Destination path.
- Protocol.
- Conflict policy.
- Created time.
- Status.

Directory tasks expand into multiple TransferItem rows while preserving relative paths.

### TransferItem

A TransferItem represents one physical file transfer.

Fields include:

- Item ID.
- Parent task ID.
- Server ID.
- Direction.
- Source path.
- Destination path.
- Temporary path.
- File size.
- Modified time.
- Optional checksum.
- Bytes transferred.
- Status.
- Retry count.
- Last error.
- Protocol.

## Queue Scheduling

Scheduling uses a hybrid model:

- Each server has an independent queue.
- Each server has upload and download concurrency limits.
- The application has a global concurrency limit.
- The global transfer view merges all server queues.
- A slow or failing server should not block unrelated server queues.

The scheduler emits state changes for the UI and persists enough state to restore unfinished work after restart.

## Resume Behavior

### File-Level Resume

Upload:

- Use a temporary remote filename such as `.filezall.<name>.part`.
- Check remote temporary file size.
- Continue upload from the remote byte offset when the protocol supports it.
- Rename temporary file to final name after successful completion.

Download:

- Use a temporary local filename such as `.filezall.<name>.part`.
- Check local temporary file size.
- Continue download from the local byte offset when the protocol supports it.
- Rename temporary file to final name after successful completion.

### Task-Level Resume

Directory transfers persist item states to the local database.

On restart:

- Completed items are skipped.
- Failed items are eligible for retry.
- Incomplete items resume from byte offset when possible.
- Missing temporary files restart from zero bytes.

### Conflict Policies

First version supports:

- Overwrite.
- Skip.
- Rename.

Conflict policy is chosen before transfer execution and recorded on the task.

## Agent Design

The Linux Agent runs as a systemd service.

Deployment flow:

1. Client connects through SSH.
2. Client detects whether Agent is installed.
3. If missing, client uploads Agent package.
4. Client writes Agent config.
5. Client installs or updates the systemd service.
6. Client starts the service and checks health.

Agent access should prefer SSH tunneling. The Agent should not require a public management port.

Agent security:

- API requires a random token.
- Token is stored on the server in Agent configuration.
- Client stores token in the OS credential store.
- Logs must not print credentials, tokens, private key contents, or passwords.

## Resource Monitoring

Agent-backed monitoring is the preferred mode.

Without Agent:

- SFTP/SSH connections can use remote shell commands for basic Linux metrics.
- FTP/FTPS connections only support file transfer and file browsing.

Monitoring requests should be periodic and lightweight. Process details are loaded on demand when the user expands a process row.

## Local Persistence

FileZall stores non-sensitive state in a local SQLite database or structured config store:

- Site metadata.
- Default local directory.
- Default remote directory.
- Protocol selection.
- Concurrency settings.
- Rate limit settings.
- Conflict policy.
- Transfer tasks.
- Transfer items.
- UI preferences.

Sensitive data is stored only in OS credential stores:

- Server password.
- SSH private key passphrase.
- Agent token.

The local database stores credential reference IDs, not secret values.

## Packaging and Distribution

Windows:

- Build the PySide6 app with PyInstaller or Nuitka.
- Package as an installer using Inno Setup or MSIX.
- Include app icon, file associations only if later needed, and first-run config directory creation.

macOS:

- Build an `.app` using PyInstaller or Nuitka.
- Package as `.dmg`.
- Leave room for signing and notarization.

Linux Agent:

- Ship as a `tar.gz` package.
- Include a systemd service file.
- Support client-driven install and upgrade through SSH.

## Testing Strategy

### Core Engine Tests

Cover:

- Queue scheduling.
- Per-server and global concurrency limits.
- Transfer task expansion.
- Transfer item state transitions.
- Resume offset calculation.
- Conflict policies.
- Task recovery after restart.

### Protocol Integration Tests

Cover:

- SFTP list, upload, download, and resume.
- FTP list, upload, download, and resume when server supports it.
- FTPS connection and certificate handling.
- Agent HTTP chunk upload, chunk download, status query, merge, and verification.

### Desktop Tests

Cover:

- Site manager flows.
- Connect and disconnect flows.
- Local directory navigation.
- Remote directory navigation.
- Queue actions.
- Process detail expansion.

Automated UI tests can be introduced after core behavior is stable. Core behavior should be tested first because it carries the highest data-loss risk.

### Packaging Smoke Tests

Cover:

- Windows installer launches.
- macOS app launches.
- Saved site can reconnect.
- Small file upload and download.
- Large file interrupted and resumed.
- Directory transfer interrupted and resumed.
- App restart restores unfinished queue state.

## Milestones

### M1: Project Skeleton

- PySide6 desktop shell.
- Independent core package.
- Local config/database setup.
- Basic test runner.

### M2: Site Manager and SFTP

- Password and SSH Key login.
- Default remote home directory.
- Local and remote dual-pane browsing.
- Single-file upload and download through SFTP.

### M3: Queue and Resume

- Hybrid queue scheduler.
- Pause, resume, cancel, retry.
- File-level resume.
- Task-level resume.
- Queue persistence.

### M4: FTP and FTPS

- FTP browsing and transfer.
- FTPS browsing and transfer.
- Protocol capability indicators.
- Monitoring degradation messages.

### M5: Linux Agent and Resource Monitoring

- Agent health check.
- SSH deployment flow.
- CPU, memory, disk, network metrics.
- Process list.
- Process detail expansion.

### M6: Agent HTTP Chunked Transfer

- Chunk upload.
- Chunk download.
- Chunk status query.
- Merge and verification.
- Queue integration.

### M7: Multi-Server and Packaging

- Multiple simultaneous connections.
- Global transfer view.
- Per-server transfer views.
- Windows installer.
- macOS app package.
- Basic release documentation.

## Open Implementation Notes

- Prefer SFTP/SSH for secure default behavior.
- FTP must be clearly marked as unencrypted.
- FTPS should verify certificates and allow explicit trust for self-signed certificates.
- Large directory enumeration must not block the UI thread.
- Transfer operations must write to temporary files before final rename.
- UI should receive progress events rather than polling internal transfer loops directly.
