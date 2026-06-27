# FileZall Performance Special Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Raise FileZall from feature-complete prototype performance toward commercial-grade responsiveness, transfer throughput visibility, and long-run stability.

**Architecture:** Work in measured increments: first add reproducible performance baselines, then remove UI update hot spots, then replace high-volume widgets with model/view virtualization, then tune transfer and Agent paths. Each milestone must include focused tests and must not regress the existing FileZall workflows.

**Tech Stack:** Python 3.12, PySide6, pytest, pytest-qt, SQLite-backed transfer queue, Paramiko/SFTP, FileZall Linux Agent.

---

## Milestone Order

1. **Performance Baseline and Low-Risk UI Hot Spots**
   - Add repeatable measurement utilities for operation duration and throughput.
   - Add baseline tests for report structure and threshold metadata.
   - Optimize `LogViewer.add_record()` so appending a log row does not rebuild the entire visible list.
   - Keep all existing log filtering, copy, and export behavior.

2. **File and Process List Virtualization**
   - Introduce a `FileEntryTableModel` backed by plain Python row data.
   - Move file panels from `QTableWidget` toward `QTableView + QAbstractTableModel`.
   - Preserve row hover, full-row selection, icons, parent directory row, context menus, keyboard shortcuts, drag/drop, and directory history.
   - Add tests for 10k+ row model operations without requiring every cell to be materialized as a widget item.

3. **Transfer Center Refresh Throttling**
   - Batch rapid transfer progress callbacks into timed UI updates.
   - Preserve final completion/failure visibility immediately.
   - Add tests proving repeated progress events coalesce into fewer table refreshes while final state is delivered.

4. **Queue Scheduler and Transfer Throughput**
   - Make queue concurrency explicit per server.
   - Add retry backoff metadata and stable pause/resume/cancel state transitions.
   - Add throughput snapshots for current speed, average speed, ETA, retry count, and failure reason.

5. **Remote Directory and Agent Acceleration**
   - Cache recent remote directory listings with explicit invalidation on refresh/create/delete/rename/upload/download.
   - Add Agent-side recursive directory scan and batch stat endpoints.
   - Use Agent batch listing when available and fall back to SFTP listing when Agent is unavailable.

6. **Long-Run Diagnostics and Stress Verification**
   - Add a diagnostic summary that captures UI refresh rate, queue size, recent errors, memory hints, and transfer counters.
   - Add scripted smoke scenarios for large local directories, large transfer queues, repeated resource refresh, and long log streams.
   - Keep live SFTP tests environment-gated and report skipped live tests clearly.

## Execution Contract

- Every milestone starts with a failing test for the behavior or performance contract.
- Focused tests must pass before moving to the next milestone.
- Full `.\.venv\Scripts\python.exe -m pytest` must pass before each commit.
- If `tests\integration\test_sftp_live.py` skips because live environment variables are absent, report that skip as expected.
- Commit each milestone separately with a message that names the performance area.

## Immediate Task 1: Log Append Hot Spot

**Files:**
- Modify: `src/filezall_desktop/log_viewer.py`
- Test: `tests/desktop/test_log_viewer.py`

- [x] **Step 1: Write failing test**

Add a test that selects an existing log row, appends another record, and asserts selection remains on the original row. The current implementation clears and rebuilds the list for every append, so the test should fail before the optimization.

- [x] **Step 2: Run focused test**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\desktop\test_log_viewer.py -k preserves_selection
```

Expected: FAIL before implementation.

- [x] **Step 3: Implement incremental append**

Update `LogViewer.add_record()` so it appends a single visible `QListWidgetItem` when the new record matches the active filter. Only `set_category_filter()` should perform a full refresh.

- [x] **Step 4: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\desktop\test_log_viewer.py
```

Expected: all log viewer tests pass.

## Immediate Task 2: Baseline Measurement Utility

**Files:**
- Create: `src/filezall_core/performance.py`
- Create: `tests/core/test_performance.py`

- [x] **Step 1: Write failing tests**

Add tests for:
- `measure_operation(name, operation)` returns elapsed milliseconds and operation result.
- `PerformanceBudget.check(result)` reports pass/fail without raising.

- [x] **Step 2: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\core\test_performance.py
```

Expected: FAIL before implementation.

- [x] **Step 3: Implement minimal measurement utilities**

Create dataclasses for `PerformanceResult`, `PerformanceBudget`, and `PerformanceBudgetCheck`. Use `time.perf_counter()` and keep the module free of PySide dependencies so it can be reused by core and desktop tests.

- [x] **Step 4: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\core\test_performance.py
```

Expected: PASS.

## Next Milestone Entry Criteria

Start Milestone 2 only after:

- Task 1 and Task 2 are committed.
- Full pytest passes.
- A short note is added to the final response with the baseline utility location and the next planned target: file list virtualization.

## Immediate Task 3: File Entry Table Model Bridge

**Files:**
- Modify: `src/filezall_desktop/widgets.py`
- Test: `tests/desktop/test_file_entry_table_model.py`

- [x] **Step 1: Write failing model test**

Add a test that loads 10,000 file entries into `FileEntryTableModel` and reads display, type, time, directory, and icon-key roles without requiring `QTableWidgetItem` materialization.

- [x] **Step 2: Implement table model**

Introduce `FileEntryTableModel` backed by plain entry objects. Keep it independent from the existing `QTableWidget` rendering path so the next migration can swap the view without changing file-entry data formatting again.

- [x] **Step 3: Write failing FilePanel bridge test**

Add a test that calls `FilePanel.set_entries()` with 10,000 entries and asserts the panel keeps the virtual model in sync while the current table behavior remains available.

- [x] **Step 4: Bridge FilePanel to the virtual model**

Create `FilePanel.entry_model`, update it from `set_entries()`, clear it for placeholder rows, and keep translated labels synchronized through `set_texts()`.

- [x] **Step 5: Run focused regression tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\desktop\test_file_entry_table_model.py
.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py -k "file_panel or directory or selected or icon"
```

Expected: all selected tests pass.

## Next Milestone 2 Target

- Replace the file-panel visual table with `QTableView + FileEntryTableModel` behind a compatibility layer.
- Preserve existing signals and helpers used by `MainWindow`: row selection, double-click, parent row, drag/drop, context menu, keyboard shortcuts, icon roles, and directory history.

## Immediate Task 4: File Panel QTableView Virtualization

**Files:**
- Modify: `src/filezall_desktop/widgets.py`
- Modify: `src/filezall_desktop/main_window.py`
- Modify: `tests/desktop/test_file_entry_table_model.py`
- Modify: `tests/desktop/test_main_window.py`

- [x] **Step 1: Write failing view migration test**

Add a test that asserts `FilePanel.table` is a `QTableView`, not a `QTableWidget`, and that it is backed by `FilePanel.entry_model`.

- [x] **Step 2: Add compatibility view**

Introduce `HoverRowTableView` with the small compatibility surface that existing `MainWindow` workflows use: `cellClicked`, `cellDoubleClicked`, `local_paths_dropped`, `item(row, column)`, `rowCount()`, `columnCount()`, `currentRow()`, `setCurrentCell()`, `setRangeSelected()`, and `horizontalHeaderItem()`.

- [x] **Step 3: Move FilePanel to model/view rendering**

Switch file panels to `QTableView + FileEntryTableModel`. Large directories now populate the model immediately and let Qt virtualize painting, replacing the previous timer-batched `QTableWidgetItem` materialization path.

- [x] **Step 4: Preserve existing interactions**

Keep full-row hover/selection painting, icons only in the first column, parent directory rows, placeholder rows, drag/drop, context menu, keyboard shortcuts, directory double-click navigation, and selected-row helpers.

- [x] **Step 5: Run verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\desktop\test_file_entry_table_model.py
.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py -k "file_panel or directory or selected or icon or shortcut or upload or download"
.\.venv\Scripts\python.exe -m pytest
```

Expected: all tests pass except the environment-gated live SFTP skip.

## Next Milestone 2 Target

- Consider extracting `FileEntryTableModel`, `HoverRowTableView`, and compatibility item wrappers into a dedicated module once process-list virtualization starts.
- Apply the same model/view strategy to the process list or begin transfer-center refresh throttling, depending on which user-visible lag is most severe during validation.

## Immediate Task 5: Transfer Center Refresh Throttling

**Files:**
- Modify: `src/filezall_desktop/main_window.py`
- Modify: `tests/desktop/test_main_window.py`

- [x] **Step 1: Write failing throttling test**

Add a test that renders an initial running transfer row, sends multiple rapid running progress updates, asserts the visible table is not rebuilt immediately, waits for the coalesced update, and then verifies a terminal completed status flushes immediately.

- [x] **Step 2: Split state update from table rendering**

Keep `_optimistic_transfer_items` and the transfer summary current on every `set_transfer_items()` call, but move table materialization into `_render_transfer_items()`.

- [x] **Step 3: Add coalesced refresh timer**

Use a single-shot `transfer_refresh_timer` to batch repeated non-terminal progress updates for the same rendered transfer item set. Store only the latest pending snapshot.

- [x] **Step 4: Preserve immediate visibility for important changes**

Render immediately when the table is empty, row count changes, transfer identity changes, or any item reaches a terminal status: completed, failed, or canceled.

- [x] **Step 5: Run verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py -k coalesces_running_progress
.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py -k "transfer_center or transfer_progress or upload or download or retry"
.\.venv\Scripts\python.exe -m pytest
```

Expected: all tests pass except the environment-gated live SFTP skip.

## Next Milestone Target

- Continue with queue scheduler and transfer throughput polish: explicit per-server concurrency, retry backoff metadata, and clearer pause/resume/cancel state transitions.
- Alternatively apply model/view virtualization to the process list if process rows become a larger UI bottleneck during validation.

## Immediate Task 6: Per-Server Queue Concurrency

**Files:**
- Modify: `src/filezall_core/transfer_settings.py`
- Modify: `src/filezall_core/queue.py`
- Modify: `src/filezall_desktop/main_window.py`
- Modify: `src/filezall_desktop/i18n.py`
- Modify: `tests/core/test_queue.py`
- Modify: `tests/desktop/test_main_window.py`

- [x] **Step 1: Write failing scheduler test**

Add a queue test that reserves one slot for `site-1` with `max_concurrent=2` and `max_concurrent_per_server=1`, verifies another `site-1` item is blocked, and verifies a `site-2` item can still run.

- [x] **Step 2: Add transfer setting**

Extend `TransferSettings` with `max_concurrent_per_server`. Keep the default compatible by treating `None` as the global max concurrency.

- [x] **Step 3: Implement queue slot accounting**

Add `can_start_transfer()`, `reserve_slot()`, and `release_slot()` to track global running count and per-server running count. Route `run_next()` through the same slot accounting.

- [x] **Step 4: Expose per-server concurrency in UI**

Add a per-server concurrency spin box to the transfer center and settings dialog. Wire it into `TransferSettings` and localize the label.

- [x] **Step 5: Run verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\core\test_queue.py
.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py -k "settings_menu_opens_dialog or concurrency_and_limit_controls"
.\.venv\Scripts\python.exe -m pytest
```

Expected: all tests pass except the environment-gated live SFTP skip.

## Next Milestone Target

- Add retry backoff metadata so retrying transfers expose next-attempt timing instead of immediately looping without user-visible timing.
- Tighten pause/resume/cancel state transitions for in-flight items if the transfer runner becomes asynchronous.

## Immediate Task 7: Retry Backoff Timing

**Files:**
- Modify: `src/filezall_core/models.py`
- Modify: `src/filezall_core/storage.py`
- Modify: `src/filezall_core/transfer_repository.py`
- Modify: `src/filezall_core/queue.py`
- Modify: `src/filezall_desktop/main_window.py`
- Modify: `tests/core/test_queue.py`
- Modify: `tests/core/test_storage.py`
- Modify: `tests/desktop/test_main_window.py`

- [x] **Step 1: Write failing retry backoff test**

Add a queue test with a controlled clock and a client that fails once. Verify the first failure becomes `RETRYING`, stores `next_retry_at`, does not immediately run before that time, and succeeds once the clock reaches the retry time.

- [x] **Step 2: Persist retry timing**

Add `TransferItem.next_retry_at`, create/migrate the `transfer_items.next_retry_at` column, and include it in repository save/select/update mapping.

- [x] **Step 3: Change retry execution semantics**

Replace immediate in-call retry loops with one attempt per scheduler call. Failed attempts below `max_attempts` move to `RETRYING` with exponential backoff timing. Due retrying items become eligible for `run_next()`.

- [x] **Step 4: Clear retry timing on progress and manual retry**

Running/completed progress writes clear `next_retry_at`. Manual retry resets the status to pending and clears retry timing.

- [x] **Step 5: Show retry timing in UI**

When a transfer row is `RETRYING` and has `next_retry_at`, show `Retrying at <timestamp>` in the status column while preserving the existing retry/failure styling.

- [x] **Step 6: Run verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\core\test_queue.py -k retry_backoff
.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py -k "next_retry_time or retry_and_failure"
.\.venv\Scripts\python.exe -m pytest
```

Expected: all tests pass except the environment-gated live SFTP skip.

## Next Milestone Target

- Tighten pause/resume/cancel state transitions for in-flight items and ensure future asynchronous runners can interrupt or settle them predictably.
- Consider surfacing retry countdown as a relative timer in the UI after the next transfer-center refresh pass.

## Immediate Task 8: Transfer State Transition Consistency

**Files:**
- Modify: `src/filezall_core/queue.py`
- Modify: `tests/core/test_queue.py`

- [x] **Step 1: Write failing state transition tests**

Add tests for retry-waiting items:
- Pause converts `RETRYING` to `PAUSED` and clears `next_retry_at`.
- Cancel converts retry-waiting items to `CANCELED` and clears `next_retry_at`.
- Manual retry converts `RETRYING` to `PENDING`, clears retry metadata, and preserves the already-counted retry attempt.

- [x] **Step 2: Update pause/resume transitions**

Allow `RETRYING` items to be paused. Clear `next_retry_at` when pausing or resuming so no stale retry timer survives a user decision.

- [x] **Step 3: Update cancel transition**

Clear `next_retry_at` when canceling unfinished items so canceled rows never keep a retry schedule.

- [x] **Step 4: Update manual retry transition**

Let manual retry force both `FAILED` and `RETRYING` items to `PENDING`. Failed items keep the previous retry-count increment behavior; retry-waiting items preserve their existing retry count because the failed attempt was already counted.

- [x] **Step 5: Run verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\core\test_queue.py -k "pauses_retrying or cancels_retrying or manual_retry_forces"
.\.venv\Scripts\python.exe -m pytest tests\core\test_queue.py
.\.venv\Scripts\python.exe -m pytest
```

Expected: all tests pass except the environment-gated live SFTP skip.

## Next Milestone Target

- Add relative retry countdown display in the transfer center.
- Evaluate process-list model/view virtualization if resource monitoring with many processes is still visibly heavy.

## Immediate Task 9: Relative Retry Countdown Display

**Files:**
- Modify: `src/filezall_desktop/main_window.py`
- Modify: `tests/desktop/test_main_window.py`

- [x] **Step 1: Write failing countdown test**

Add a transfer-center test that sets a controlled UI clock, renders a retrying transfer with `next_retry_at`, and expects the status column to show `Retrying in 2s` instead of an absolute timestamp.

- [x] **Step 2: Add retry countdown timer**

Add a `transfer_retry_countdown_timer` owned by `MainWindow`. Start it only when the rendered transfer snapshot contains a future `RETRYING` item, and stop it when no future retry timers remain.

- [x] **Step 3: Render relative retry text**

Update transfer status text so future retry times display as `Retrying in Ns`; due retry rows display `Retrying now`.

- [x] **Step 4: Refresh status cells without rebuilding transfer rows**

On countdown timer ticks, update only the status-column text for the already-rendered transfer rows. Keep the existing coalesced transfer table rendering path unchanged.

- [x] **Step 5: Run verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py -k "next_retry_time or relative_retry_countdown or retry_and_failure"
.\.venv\Scripts\python.exe -m pytest
```

Expected: all tests pass except the environment-gated live SFTP skip.

## Next Milestone Target

- Evaluate process-list model/view virtualization if resource monitoring with many processes is still visibly heavy.
- Add a diagnostics bundle if performance validation starts producing local-only crash or latency evidence.

## Immediate Task 10: Process List Model/View Virtualization

**Files:**
- Modify: `src/filezall_desktop/widgets.py`
- Modify: `src/filezall_desktop/main_window.py`
- Modify: `tests/desktop/test_main_window.py`

- [x] **Step 1: Write failing process table migration test**

Add a desktop test that requires the resource-monitor process list to use a `QTableView`
with an attached model instead of a `QTableWidget`, so large process snapshots do not
create thousands of per-cell widgets/items.

- [x] **Step 2: Add process table model**

Add `ProcessTableModel` with PID, user, name, CPU, and memory columns. Preserve the
existing `DisplayRole` text and PID `UserRole` contract used by process detail and
context actions.

- [x] **Step 3: Move process UI to HoverRowTableView**

Replace the process `HoverRowTableWidget` with `HoverRowTableView`, keeping full-row
hover/selection styling, single-row selection, double-click process detail, and
right-click stop/restart/copy PID actions.

- [x] **Step 4: Run targeted verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py -k "process_table or process_context or resource_monitor_has_time_range or renders_resource_snapshot" -vv
```

Expected: process rendering, sort/filter, detail, and context actions pass with the
model/view table.

## Next Milestone Target

- Add user-exportable diagnostics bundle coverage for GUI crashes, resource refresh
  timing, queue state, and recent logs.
- Continue measuring high-volume transfer and large-directory paths with evidence
  before deeper asynchronous transfer-runner changes.

## Immediate Task 11: Diagnostic State Snapshot

**Files:**
- Modify: `src/filezall_core/diagnostics.py`
- Modify: `src/filezall_desktop/main_window.py`
- Modify: `tests/core/test_diagnostics.py`
- Modify: `tests/desktop/test_main_window.py`

- [x] **Step 1: Write failing diagnostic state tests**

Add a core diagnostics test requiring `state/snapshot.json` to be included and
redacted, plus a desktop export test requiring resource-refresh status, queue counts,
and recent error logs to be captured from the live UI.

- [x] **Step 2: Add optional state provider to diagnostics builder**

Let `DiagnosticPackageBuilder` accept a callable state provider and write its output to
`state/snapshot.json`. Recursively redact sensitive keys and sensitive string values
before writing the archive.

- [x] **Step 3: Add MainWindow UI state snapshot**

Export resource-refresh timer/running state, transfer queue status counts, recent logs,
Agent state, and UI sizing/context hints when the user chooses Export Diagnostics.

- [x] **Step 4: Run targeted verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\core\test_diagnostics.py::test_diagnostic_package_includes_redacted_state_snapshot tests\desktop\test_main_window.py::test_main_window_diagnostic_package_includes_ui_state_snapshot -vv
```

Expected: both new diagnostic-state tests pass.

## Next Milestone Target

- Add a scripted performance smoke command that exercises large transfer queues and
  large directory render paths without needing a live server.
- Use the new diagnostic snapshot as the artifact for future slow-path reports.

## Immediate Task 12: Scripted Desktop Performance Smoke

**Files:**
- Create: `src/filezall_desktop/performance_smoke.py`
- Create: `scripts/performance-smoke.ps1`
- Modify: `pyproject.toml`
- Modify: `tests/desktop/test_performance_smoke.py`
- Modify: `tests/test_packaging_files.py`

- [x] **Step 1: Write failing smoke tests**

Add a desktop smoke test that requires a report for large-directory and large-transfer
queue scenarios, plus a script-contract test requiring the PowerShell entry point to
call the Python smoke module.

- [x] **Step 2: Implement desktop smoke module**

Create synthetic `LocalFileEntry` and `TransferItem` data, run the actual Qt desktop
render paths with an offscreen `QApplication`, measure elapsed time with the existing
performance helpers, and include the live diagnostic state snapshot in the report.

- [x] **Step 3: Add runnable command entry points**

Add `filezall-performance-smoke` to `pyproject.toml` and add
`scripts/performance-smoke.ps1` for Windows validation. Support environment overrides
for directory rows, transfer rows, and output path.

- [x] **Step 4: Run targeted verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\desktop\test_performance_smoke.py tests\test_packaging_files.py::test_performance_smoke_script_runs_desktop_smoke_module -vv
.\.venv\Scripts\python.exe -m filezall_desktop.performance_smoke --directory-rows 20 --transfer-rows 15 --output .filezall-smoke-performance.json
```

Expected: tests pass and the module writes a JSON report with `status`, `scenarios`,
and `diagnostic_state`.

## Next Milestone Target

- Add smoke-report trend comparison or baseline thresholds so repeated runs can show
  whether a change improved or worsened UI responsiveness.
- Continue transfer-center virtualization work if large queue smoke shows QTableWidget
  rendering remains the next hot path.

## Immediate Task 13: Performance Smoke Baseline Comparison

**Files:**
- Modify: `src/filezall_desktop/performance_smoke.py`
- Modify: `scripts/performance-smoke.ps1`
- Modify: `tests/desktop/test_performance_smoke.py`
- Modify: `tests/test_packaging_files.py`

- [x] **Step 1: Write failing baseline comparison tests**

Add tests requiring smoke reports to compare current scenario timing against a prior
baseline report, including per-scenario status, delta milliseconds, and delta percent.
Add a CLI test proving `--baseline` writes the comparison into the output report.

- [x] **Step 2: Implement comparison semantics**

Compare matching scenarios by `elapsed_ms`. Mark scenarios as `improved`, `unchanged`,
or `regressed` using a small tolerance, and mark the overall comparison as `regressed`
if any scenario regresses.

- [x] **Step 3: Wire CLI and PowerShell baseline options**

Add `--baseline` to the Python CLI and `FILEZALL_PERF_BASELINE` to
`scripts/performance-smoke.ps1` so Windows smoke runs can compare against a saved
`performance-smoke.json`.

- [x] **Step 4: Run targeted verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\desktop\test_performance_smoke.py tests\test_packaging_files.py::test_performance_smoke_script_runs_desktop_smoke_module -vv
.\.venv\Scripts\python.exe -m filezall_desktop.performance_smoke --directory-rows 4 --transfer-rows 3 --baseline .filezall-smoke-baseline.json --output .filezall-smoke-current.json
```

Expected: tests pass and the generated report contains `baseline.comparison`.

## Next Milestone Target

- Use the smoke report to decide whether the transfer center should move from
  `QTableWidget` to `QTableView + model`.
- Add repeated resource-refresh and long-log-stream smoke scenarios if UI stalls are
  observed outside file and transfer tables.

## Immediate Task 14: Transfer Center Model/View Virtualization

**Files:**
- Modify: `src/filezall_desktop/main_window.py`
- Modify: `src/filezall_desktop/widgets.py`
- Modify: `tests/desktop/test_main_window.py`

- [x] **Step 1: Write failing transfer table migration test**

Add a desktop test requiring the transfer center table to use a model-backed
`QTableView` instead of `QTableWidget`, while preserving the public compatibility
methods used by existing desktop tests.

- [x] **Step 2: Add transfer table model**

Create `TransferTableModel` for server, direction, file, progress, speed, remaining,
retry count, failure reason, and status columns. Preserve the task-id `UserRole` used
by pause/resume/cancel/retry actions.

- [x] **Step 3: Preserve retry countdown and status colors**

Move retry countdown rendering into model data and refresh only the status column on
timer ticks. Add virtual-item background compatibility so existing status color checks
continue to work.

- [x] **Step 4: Run targeted verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py -k "transfer_table or transfer_center or transfer_retry or direct_upload" -vv
.\.venv\Scripts\python.exe -m pytest tests\desktop\test_performance_smoke.py -vv
```

Expected: transfer rendering, action buttons, retry countdown, status color, and
performance smoke tests pass with the model/view table.

## Next Milestone Target

- Add repeated resource-refresh and long-log-stream smoke scenarios to widen
  performance coverage beyond file and transfer tables.
- Start remote directory caching and explicit invalidation if real-server navigation
  still feels slow after UI-side table virtualization.

## Immediate Task 15: Broaden Desktop Performance Smoke Scenarios

**Files:**
- Modify: `src/filezall_desktop/performance_smoke.py`
- Modify: `scripts/performance-smoke.ps1`
- Modify: `tests/desktop/test_performance_smoke.py`
- Modify: `tests/test_packaging_files.py`

- [x] **Step 1: Write failing smoke coverage tests**

Extend the desktop smoke test so the report must include `repeated_resource_refresh`
and `long_log_stream`, and require the script contract to expose environment variables
for those sample sizes.

- [x] **Step 2: Add repeated resource refresh scenario**

Generate synthetic `ResourceSnapshot` samples and run the real
`MainWindow.set_resource_snapshot()` path so labels, chart history, disk selectors,
and process model updates are covered without a live server.

- [x] **Step 3: Add long log stream scenario**

Append synthetic log rows through `MainWindow.append_log()` so the real
`TransferLogService` and `LogViewer.add_record()` path is measured.

- [x] **Step 4: Wire CLI and PowerShell parameters**

Add `--resource-samples` and `--log-rows` to the Python CLI, plus
`FILEZALL_PERF_RESOURCE_SAMPLES` and `FILEZALL_PERF_LOG_ROWS` to the Windows script.

- [x] **Step 5: Run targeted verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\desktop\test_performance_smoke.py -vv
.\.venv\Scripts\python.exe -m filezall_desktop.performance_smoke --directory-rows 4 --transfer-rows 3 --resource-samples 3 --log-rows 4 --output .filezall-smoke-performance.json
```

Expected: the smoke report contains four scenarios and diagnostic state reflects the
log count and resource chart sample count.

## Next Milestone Target

- Start remote directory caching with explicit invalidation on refresh, create/delete,
  rename, upload, and download.
- Add Agent batch listing only after the cache layer has tests around freshness and
  invalidation semantics.

## Immediate Task 16: Cache Remote Directory Listings With Explicit Invalidation

**Files:**
- Modify: `src/filezall_desktop/controller.py`
- Modify: `src/filezall_desktop/main_window.py`
- Modify: `tests/desktop/test_controller.py`

- [x] **Step 1: Write remote cache freshness tests**

Add controller tests proving repeated navigation reuses cached remote directory
entries, explicit refresh bypasses the cache, and a remote upload invalidates the
cached parent directory before the next list.

- [x] **Step 2: Add controller-side directory cache**

Cache remote directory entries per connected site and path in
`MainWindowController.load_remote_directory()`. Reconnect and disconnect clear the
cache, and the initial default directory returned by connect is cached.

- [x] **Step 3: Invalidate cache on remote mutations**

Invalidate affected remote paths for upload, download, delete, create directory,
create file, and rename. Path invalidation removes both the exact cached directory
and cached child directories for the same connection.

- [x] **Step 4: Preserve explicit refresh semantics**

Add `force_refresh` to controller directory loading and pass it from the remote
Refresh/F5 path so user-triggered refreshes always hit the server.

- [x] **Step 5: Run targeted verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\desktop\test_controller.py -k "cached_remote_directory or force_refresh_bypasses_remote_directory_cache or remote_mutations_invalidate" -vv
.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py -k "remote_refresh or refresh_buttons or remote_directory or remote_history" -vv
```

Expected: controller cache semantics and main-window refresh/navigation flows pass.

## Next Milestone Target

- Add Agent batch listing support to reduce deep remote directory traversal round
  trips after cache freshness and invalidation behavior is locked down.
- Extend smoke coverage to include cached versus forced remote directory navigation
  once a deterministic fake remote listing workload is available.

## Immediate Task 17: Add Agent Batch Directory Walk

**Files:**
- Modify: `agent/filezall_agent/files.py`
- Modify: `agent/filezall_agent/server.py`
- Modify: `src/filezall_core/agent_file_client.py`
- Modify: `src/filezall_core/directory_plan.py`
- Modify: `tests/agent/test_agent_files.py`
- Modify: `tests/agent/test_agent_http.py`
- Modify: `tests/core/test_agent_file_client.py`
- Modify: `tests/core/test_directory_plan.py`

- [x] **Step 1: Write batch walk tests**

Add service, HTTP, client, and directory-plan tests proving a nested remote
directory can be walked through one Agent endpoint and that directory download
planning uses `client.walk_directory()`.

- [x] **Step 2: Add Agent file-service walk**

Implement `AgentFileService.walk_directory()` to return file entries from a
subtree in one service call while preserving the same entry payload format as
`list_directory()`.

- [x] **Step 3: Expose `/files/walk`**

Add an authenticated GET route returning `{"entries": ...}` for the requested
path so installed Agents can serve recursive file listings without one HTTP call
per nested directory.

- [x] **Step 4: Use batch walk in core client and planning**

Update `AgentHttpFileClient.walk_directory()` to call `/files/walk`, and update
`plan_remote_directory()` to call `client.walk_directory(root)` so optimized
clients are honored.

- [x] **Step 5: Run targeted verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\agent\test_agent_files.py::test_agent_file_service_walks_directory_tree_in_one_call tests\agent\test_agent_http.py::test_agent_http_server_serves_files_chunks_and_resources tests\core\test_agent_file_client.py::test_agent_file_client_walks_directory_with_single_agent_request tests\core\test_directory_plan.py::test_plan_remote_directory_uses_client_batch_walk -vv
```

Expected: Agent service, HTTP route, Agent client, and directory planning all
use the new batch walk behavior.

## Next Milestone Target

- Add a deterministic performance-smoke scenario comparing cached navigation and
  forced remote refresh.
- Continue connection-state and transfer-runner performance work after the file
  listing path has measurable coverage.

## Immediate Task 18: Measure Cached and Forced Remote Directory Navigation

**Files:**
- Modify: `src/filezall_desktop/performance_smoke.py`
- Modify: `scripts/performance-smoke.ps1`
- Modify: `tests/desktop/test_performance_smoke.py`
- Modify: `tests/test_packaging_files.py`

- [x] **Step 1: Extend smoke contract tests**

Require performance reports to include `remote_directory_cache` and
`remote_directory_forced_refresh`, plus diagnostic counters proving cached loads
avoid remote list calls while forced refreshes still hit the session.

- [x] **Step 2: Add deterministic remote session workload**

Add a fake remote session with configurable row and sample counts, connect it
through `MainWindowController`, and measure cached versus forced
`load_remote_directory()` calls.

- [x] **Step 3: Expose CLI and script controls**

Add `--remote-rows`, `--remote-samples`, `--remote-cache-budget-ms`, and
`--remote-force-budget-ms` to the Python CLI. Add
`FILEZALL_PERF_REMOTE_ROWS` and `FILEZALL_PERF_REMOTE_SAMPLES` to the Windows
smoke script.

- [x] **Step 4: Run targeted verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\desktop\test_performance_smoke.py tests\test_packaging_files.py::test_performance_smoke_script_runs_desktop_smoke_module -vv
```

Expected: smoke reports include remote cache and forced-refresh scenarios, and
script-level environment variables are wired.

## Next Milestone Target

- Continue connection-state and transfer-runner performance work.
- Add richer diagnostics around retry and reconnect workloads before tuning
  transfer concurrency defaults.

## Immediate Task 19: Add Transfer Retry Diagnostics

**Files:**
- Modify: `src/filezall_core/queue.py`
- Modify: `src/filezall_desktop/main_window.py`
- Modify: `tests/core/test_queue.py`
- Modify: `tests/desktop/test_main_window.py`

- [x] **Step 1: Write queue diagnostic tests**

Add a core queue test proving diagnostics report total items, status counts,
active concurrency slots, retry backlog split into ready/waiting, next retry
time, and recent failed/retrying reasons.

- [x] **Step 2: Add queue diagnostic snapshot**

Implement `TransferQueue.diagnostic_snapshot()` so future concurrency and retry
tuning has a stable structured state surface instead of relying only on visible
table rows.

- [x] **Step 3: Enrich UI diagnostic package state**

Extend the main-window diagnostic snapshot with transfer retry totals, waiting
retry counts, next retry time, and recent failed/retrying reasons using the
window transfer status clock for deterministic output.

- [x] **Step 4: Run targeted verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\core\test_queue.py tests\desktop\test_main_window.py::test_main_window_diagnostic_package_includes_ui_state_snapshot tests\desktop\test_performance_smoke.py -vv
```

Expected: queue behavior still passes and diagnostic exports include retry and
failure details.

## Next Milestone Target

- Add reconnect/timeout classification metrics around connection and heartbeat
  failures.
- Use the new retry diagnostics before changing transfer concurrency defaults.

## Immediate Task 20: Add Connection and Heartbeat Diagnostics

**Files:**
- Modify: `src/filezall_desktop/main_window.py`
- Modify: `tests/desktop/test_main_window.py`

- [x] **Step 1: Write connection diagnostics test**

Add a main-window test proving a failed connection and heartbeat failure are
represented in the diagnostic state with current connection state, heartbeat
timer status, attempt/failure counts, and last error messages.

- [x] **Step 2: Track connection counters**

Record connection attempts, failed connection count, and the latest classified
connection error for synchronous and background connection paths.

- [x] **Step 3: Track heartbeat failures**

Record heartbeat failure count and latest heartbeat failure message while
preserving existing log de-duplication behavior.

- [x] **Step 4: Export structured diagnostic state**

Add a `connection` block to the main-window diagnostic snapshot with status
light state, tooltip, running flag, heartbeat timer state, counters, and recent
errors.

- [x] **Step 5: Run targeted verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\desktop\test_main_window.py -k "connection or heartbeat or diagnostic_package" -vv
```

Expected: existing connection status light behavior still passes and diagnostic
state includes structured connection/heartbeat failure details.

## Next Milestone Target

- Use retry and connection diagnostics to tune transfer concurrency defaults.
- Add timeout/reconnect stress scenarios to performance smoke before changing
  runtime defaults.

## Immediate Task 21: Add Heartbeat Failure Performance Smoke

**Files:**
- Modify: `src/filezall_desktop/performance_smoke.py`
- Modify: `scripts/performance-smoke.ps1`
- Modify: `tests/desktop/test_performance_smoke.py`
- Modify: `tests/test_packaging_files.py`

- [x] **Step 1: Extend smoke expectations**

Require the performance report to include
`heartbeat_failure_diagnostics`, verify the connection diagnostic state records
all heartbeat failures, and preserve the existing de-duplicated log behavior.

- [x] **Step 2: Add heartbeat failure workload**

Add a fake smoke controller with queued heartbeat results and measure repeated
`MainWindow._handle_heartbeat_tick()` failure handling through the real status
light, log, and diagnostic paths.

- [x] **Step 3: Expose script controls**

Add `--heartbeat-samples` and `--heartbeat-budget-ms` to the Python CLI, plus
`FILEZALL_PERF_HEARTBEAT_SAMPLES` to the PowerShell smoke script.

- [x] **Step 4: Run targeted verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\desktop\test_performance_smoke.py tests\test_packaging_files.py::test_performance_smoke_script_runs_desktop_smoke_module -vv
```

Expected: heartbeat failure diagnostics are measured and script wiring exposes
the sample count.

## Next Milestone Target

- Tune transfer concurrency defaults using the retry, connection, and heartbeat
  diagnostic baselines now captured in smoke reports.
- Add a bounded reconnect-state machine only after timeout/retry behavior is
  covered by measurable scenarios.

## Immediate Task 22: Tune Default Transfer Concurrency

**Files:**
- Modify: `src/filezall_core/transfer_settings.py`
- Modify: `tests/core/test_transfer_settings.py`
- Modify: `tests/desktop/test_main_window.py`

- [x] **Step 1: Write default settings tests**

Add coverage that the default transfer settings use four total concurrent
transfers and two concurrent transfers per server, with no default speed limit.

- [x] **Step 2: Update UI default expectations**

Verify the transfer center and Settings dialog show the tuned defaults before
any user override is applied.

- [x] **Step 3: Apply conservative throughput defaults**

Change `TransferSettings` defaults from total `2` and implicit per-server `2`
to total `4` and per-server `2`, improving throughput while limiting pressure
on a single server.

- [x] **Step 4: Run targeted verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\core\test_queue.py tests\core\test_transfer_settings.py tests\desktop\test_main_window.py -k "settings_menu or transfer_settings or concurrency or transfer_center" -vv
```

Expected: queue concurrency behavior and transfer-center controls pass with the
new defaults.

## Next Milestone Target

- Add a bounded reconnect-state machine only after timeout/retry behavior is
  covered by measurable scenarios.
- Continue transfer-runner tuning for pause/resume consistency and rate-limit
  enforcement.

## Immediate Task 23: Enforce Upload Rate Limit in Transfer Runner

**Files:**
- Modify: `src/filezall_core/transfer_runner.py`
- Modify: `src/filezall_core/queue.py`
- Modify: `tests/core/test_transfer_runner.py`

- [x] **Step 1: Write runner throttling test**

Add a transfer runner test with an injected clock and sleeper proving upload
progress is delayed when `bytes_per_second_limit` is set.

- [x] **Step 2: Add testable throttle hooks**

Allow `TransferRunner` to receive a throttle clock and sleeper, defaulting to
real monotonic time and `sleep`, so production behavior can be tested without
slowing the suite.

- [x] **Step 3: Throttle upload progress**

Apply a small transfer throttle around upload progress callbacks. The throttle
calculates expected elapsed time from transferred bytes and configured limit,
then sleeps only for the missing time.

- [x] **Step 4: Wire queue settings to runner**

Pass `TransferQueue.settings.bytes_per_second_limit` into `TransferRunner.run_item()`
so the existing transfer limit controls affect queued uploads.

- [x] **Step 5: Run targeted verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\core\test_transfer_runner.py tests\core\test_queue.py -vv
```

Expected: upload throttling, transfer metrics, retry, and queue concurrency tests
pass.

## Next Milestone Target

- Add bounded reconnect-state-machine tests and implementation.
- Extend rate-limit behavior to downloads once the remote clients expose download
  progress callbacks consistently.

## Immediate Task 24: Add Bounded Connection Recovery State

**Files:**
- Add: `src/filezall_core/connection_recovery.py`
- Add: `tests/core/test_connection_recovery.py`

- [x] **Step 1: Write recovery state tests**

Add tests proving repeated failures schedule bounded exponential backoff, block
after the maximum attempt count, report readiness only when the retry time is
due, and reset cleanly after success.

- [x] **Step 2: Implement recovery state model**

Add `ConnectionRecoveryState` and immutable snapshots for `idle`, `waiting`,
and `blocked` states. Keep the module independent from UI behavior so it can be
integrated safely into heartbeat handling later.

- [x] **Step 3: Run targeted verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\core\test_connection_recovery.py -vv
```

Expected: recovery backoff, readiness, blocking, and reset behavior pass.

## Next Milestone Target

- Integrate the bounded recovery state into heartbeat handling with explicit
  user-visible logs and diagnostic state.
- Extend rate-limit behavior to downloads once remote clients expose download
  progress callbacks consistently.
