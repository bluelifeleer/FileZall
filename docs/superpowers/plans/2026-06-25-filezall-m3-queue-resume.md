# FileZall M3 Queue and Resume Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent transfer tasks, a testable queue scheduler, pause/resume/cancel/retry controls, file-level resume using `.filezall.*.part` files, and task recovery after application restart.

**Architecture:** Keep transfer state and scheduling in `filezall_core`; desktop code only displays queue rows and calls controller actions. M3 introduces a resume-capable protocol boundary and a synchronous queue runner that can be tested deterministically with fake clients before later milestones add background workers and multi-server concurrency.

**Tech Stack:** Python 3.12 in `.venv`, pytest, SQLite, dataclasses, pathlib, PySide6, existing Paramiko SFTP adapter, and fake protocol clients for deterministic tests.

---

## Scope

This plan implements M3 from `docs/superpowers/specs/2026-06-24-filezall-design.md`:

- Hybrid queue foundations with per-server queues and global status view.
- Pause, resume, cancel, retry at task/item level.
- File-level resume for single-file upload and download.
- Task-level resume by persisting task/item state to SQLite.
- Desktop transfer center actions wired to the queue controller.

This plan does not implement FTP/FTPS, Agent HTTP chunking, background thread pools, true multi-server parallel transfer execution, resource monitoring, packaging installers, or directory recursion across remote trees. M3 creates the queue/resume foundation that later milestones expand.

## File Structure

- Modify: `src/filezall_core/models.py` - add queue status helpers and transfer item state transitions.
- Modify: `src/filezall_core/storage.py` - ensure transfer tables support resume metadata and status updates.
- Create: `src/filezall_core/transfer_repository.py` - CRUD for `TransferTask` and `TransferItem`.
- Create: `src/filezall_core/resume.py` - part-path and offset calculation helpers.
- Modify: `src/filezall_core/protocols.py` - add M3 resume-capable protocol methods.
- Modify: `src/filezall_core/sftp_adapter.py` - implement SFTP size checks and offset upload/download.
- Create: `src/filezall_core/transfer_runner.py` - execute one `TransferItem` through a protocol client.
- Create: `src/filezall_core/queue.py` - deterministic queue scheduler and task actions.
- Modify: `src/filezall_desktop/controller.py` - expose queue actions.
- Modify: `src/filezall_desktop/main_window.py` - wire transfer center buttons.
- Modify: `src/filezall_desktop/widgets.py` - render transfer rows and queue action controls.
- Create: `tests/core/test_transfer_repository.py`.
- Create: `tests/core/test_resume.py`.
- Create: `tests/core/test_transfer_runner.py`.
- Create: `tests/core/test_queue.py`.
- Modify: `tests/core/test_protocols.py`.
- Modify: `tests/core/test_sftp_adapter.py`.
- Modify: `tests/desktop/test_controller.py`.
- Modify: `tests/desktop/test_main_window.py`.

## Task 1: Transfer Repository

**Files:**
- Create: `src/filezall_core/transfer_repository.py`
- Test: `tests/core/test_transfer_repository.py`

- [ ] **Step 1: Write failing repository tests**

Create `tests/core/test_transfer_repository.py`:

```python
from pathlib import Path, PurePosixPath

from filezall_core.models import ConflictPolicy, Direction, Protocol, TransferStatus, TransferTask
from filezall_core.storage import initialize_database
from filezall_core.transfer_repository import TransferRepository


def test_transfer_repository_saves_task_and_items(tmp_path: Path) -> None:
    database = tmp_path / "filezall.sqlite3"
    initialize_database(database)
    repository = TransferRepository(database)
    task = TransferTask(
        id="task-1",
        server_id="site-1",
        direction=Direction.UPLOAD,
        source_path=tmp_path,
        destination_path=PurePosixPath("/home/deploy"),
        protocol=Protocol.SFTP,
        conflict_policy=ConflictPolicy.OVERWRITE,
    )
    item = task.create_item(
        item_id="item-1",
        relative_path=PurePosixPath("app.zip"),
        size_bytes=4096,
    )

    repository.save_task(task, [item])

    assert repository.get_task("task-1") == task
    assert repository.list_items("task-1") == [item]


def test_transfer_repository_updates_item_progress_and_status(tmp_path: Path) -> None:
    database = tmp_path / "filezall.sqlite3"
    initialize_database(database)
    repository = TransferRepository(database)
    task = TransferTask(
        id="task-1",
        server_id="site-1",
        direction=Direction.DOWNLOAD,
        source_path=PurePosixPath("/home/deploy"),
        destination_path=tmp_path,
        protocol=Protocol.SFTP,
        conflict_policy=ConflictPolicy.OVERWRITE,
    )
    item = task.create_item("item-1", PurePosixPath("app.zip"), size_bytes=4096)
    repository.save_task(task, [item])

    repository.update_item_progress("item-1", bytes_transferred=2048, status=TransferStatus.RUNNING)

    updated = repository.get_item("item-1")
    assert updated.bytes_transferred == 2048
    assert updated.status == TransferStatus.RUNNING


def test_transfer_repository_lists_recoverable_items_after_restart(tmp_path: Path) -> None:
    database = tmp_path / "filezall.sqlite3"
    initialize_database(database)
    repository = TransferRepository(database)
    task = TransferTask(
        id="task-1",
        server_id="site-1",
        direction=Direction.UPLOAD,
        source_path=tmp_path,
        destination_path=PurePosixPath("/home/deploy"),
        protocol=Protocol.SFTP,
        conflict_policy=ConflictPolicy.OVERWRITE,
    )
    pending = task.create_item("pending", PurePosixPath("pending.zip"), size_bytes=10)
    completed = task.create_item("done", PurePosixPath("done.zip"), size_bytes=10).with_progress(10)
    repository.save_task(task, [pending, completed])

    recoverable = repository.list_recoverable_items()

    assert [item.id for item in recoverable] == ["pending"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_transfer_repository.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'filezall_core.transfer_repository'
```

- [ ] **Step 3: Implement `TransferRepository`**

Create `src/filezall_core/transfer_repository.py` with:

- `save_task(task, items)` upserts one task and its items.
- `get_task(task_id)` returns `TransferTask | None`.
- `get_item(item_id)` returns `TransferItem | None`.
- `list_items(task_id)` returns items ordered by `created_at`.
- `list_recoverable_items()` returns non-completed and non-canceled items.
- `update_item_progress(item_id, bytes_transferred, status, last_error=None)` updates progress fields.

Use ISO strings for datetime fields and round-trip `Path`/`PurePosixPath` based on `Direction`.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_transfer_repository.py -v
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/transfer_repository.py tests/core/test_transfer_repository.py
git commit -m "feat: add transfer repository"
```

## Task 2: Resume Helpers

**Files:**
- Create: `src/filezall_core/resume.py`
- Test: `tests/core/test_resume.py`

- [ ] **Step 1: Write failing resume tests**

Create `tests/core/test_resume.py`:

```python
from pathlib import Path, PurePosixPath

from filezall_core.models import Direction, Protocol, TransferItem
from filezall_core.resume import local_resume_offset, part_path_for


def test_part_path_for_local_and_remote_paths() -> None:
    assert part_path_for(Path("D:/Downloads/app.zip")) == Path("D:/Downloads/.filezall.app.zip.part")
    assert part_path_for(PurePosixPath("/home/deploy/app.zip")) == PurePosixPath("/home/deploy/.filezall.app.zip.part")


def test_local_resume_offset_uses_existing_part_size(tmp_path: Path) -> None:
    part = tmp_path / ".filezall.app.zip.part"
    part.write_bytes(b"abc")
    item = TransferItem(
        id="item-1",
        task_id="task-1",
        server_id="site-1",
        direction=Direction.DOWNLOAD,
        source_path=PurePosixPath("/home/deploy/app.zip"),
        destination_path=tmp_path / "app.zip",
        temporary_path=part,
        size_bytes=10,
        protocol=Protocol.SFTP,
    )

    assert local_resume_offset(item) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_resume.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'filezall_core.resume'
```

- [ ] **Step 3: Implement helpers**

Create `src/filezall_core/resume.py`:

```python
from __future__ import annotations

from pathlib import Path, PurePosixPath

from filezall_core.models import TransferItem


def part_path_for(path: Path | PurePosixPath) -> Path | PurePosixPath:
    return path.with_name(f".filezall.{path.name}.part")


def local_resume_offset(item: TransferItem) -> int:
    if isinstance(item.temporary_path, Path) and item.temporary_path.exists():
        return min(item.temporary_path.stat().st_size, item.size_bytes)
    return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_resume.py -v
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/resume.py tests/core/test_resume.py
git commit -m "feat: add resume path helpers"
```

## Task 3: Resume-Capable Protocol Boundary

**Files:**
- Modify: `src/filezall_core/protocols.py`
- Test: `tests/core/test_protocols.py`

- [ ] **Step 1: Extend fake-client tests**

Append to `tests/core/test_protocols.py`:

```python
def test_fake_remote_client_reports_remote_size_and_resume_calls(tmp_path: Path) -> None:
    client = FakeRemoteClient(entries={}, home=PurePosixPath("/home/deploy"))
    local_file = tmp_path / "app.zip"
    local_file.write_bytes(b"abcdef")
    remote_part = PurePosixPath("/home/deploy/.filezall.app.zip.part")
    client.remote_sizes[remote_part] = 3

    assert client.remote_size(remote_part) == 3

    client.upload_file_range(local_file, remote_part, offset=3)
    client.download_file_range(PurePosixPath("/home/deploy/app.zip"), tmp_path / ".part", offset=2)
    client.rename(remote_part, PurePosixPath("/home/deploy/app.zip"))

    assert client.range_uploads == [(local_file, remote_part, 3)]
    assert client.range_downloads == [(PurePosixPath("/home/deploy/app.zip"), tmp_path / ".part", 2)]
    assert client.renames == [(remote_part, PurePosixPath("/home/deploy/app.zip"))]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_protocols.py -v
```

Expected:

```text
AttributeError
```

- [ ] **Step 3: Extend `RemoteFileClient` and `FakeRemoteClient`**

Add methods:

- `remote_size(path) -> int | None`
- `upload_file_range(local_path, remote_path, offset)`
- `download_file_range(remote_path, local_path, offset)`
- `rename(source_path, destination_path)`

Keep existing M2 methods intact.

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_protocols.py -v
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/protocols.py tests/core/test_protocols.py
git commit -m "feat: extend protocol interface for resume"
```

## Task 4: SFTP Resume Methods

**Files:**
- Modify: `src/filezall_core/sftp_adapter.py`
- Modify: `tests/core/test_sftp_adapter.py`

- [ ] **Step 1: Add failing SFTP resume tests**

Append tests for:

- `remote_size()` returning `None` when Paramiko raises `FileNotFoundError`.
- `upload_file_range()` opens remote file in append mode and seeks local file to offset.
- `download_file_range()` requests `getfo()` or equivalent range-safe behavior.
- `rename()` delegates to SFTP rename.

Use fake Paramiko objects and `io.BytesIO` to avoid real network.

- [ ] **Step 2: Run SFTP tests to verify failures**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_sftp_adapter.py -v
```

Expected:

```text
At least one AttributeError for missing resume method.
```

- [ ] **Step 3: Implement SFTP resume methods**

Implementation requirements:

- `remote_size(path)` uses SFTP `stat(str(path)).st_size`.
- Missing remote file returns `None`.
- `upload_file_range(local_path, remote_path, offset)` appends bytes from local offset to remote part file.
- `download_file_range(remote_path, local_path, offset)` appends remote bytes from offset to local part file.
- `rename(source, destination)` uses SFTP rename.

- [ ] **Step 4: Run SFTP tests to verify they pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_sftp_adapter.py -v
```

Expected:

```text
All SFTP adapter tests pass.
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/sftp_adapter.py tests/core/test_sftp_adapter.py
git commit -m "feat: add SFTP resume operations"
```

## Task 5: Transfer Runner

**Files:**
- Create: `src/filezall_core/transfer_runner.py`
- Test: `tests/core/test_transfer_runner.py`

- [ ] **Step 1: Write failing runner tests**

Create tests covering:

- Upload resumes from remote `.part` size and renames on completion.
- Download resumes from local `.part` size and renames on completion.
- Repository progress is updated after successful transfer.
- Runner records failed status and error message when client raises.

Use `FakeRemoteClient`, `TransferRepository`, and temp files.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_transfer_runner.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'filezall_core.transfer_runner'
```

- [ ] **Step 3: Implement `TransferRunner`**

Create `src/filezall_core/transfer_runner.py` with:

- `run_item(item, client) -> TransferItem`
- upload path: remote part path, remote offset, range upload, remote rename.
- download path: local part path, local offset, range download, local replace/rename.
- repository progress updates for running/completed/failed states.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_transfer_runner.py -v
```

Expected:

```text
All transfer runner tests pass.
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/transfer_runner.py tests/core/test_transfer_runner.py
git commit -m "feat: add resumable transfer runner"
```

## Task 6: Queue Scheduler and Actions

**Files:**
- Create: `src/filezall_core/queue.py`
- Test: `tests/core/test_queue.py`

- [ ] **Step 1: Write failing queue tests**

Create tests covering:

- Adding a task persists it and exposes queued rows.
- `pause_task(task_id)` changes pending/running items to paused.
- `resume_task(task_id)` changes paused items back to pending.
- `cancel_task(task_id)` marks non-completed items canceled.
- `retry_failed(task_id)` increments retry count and resets failed items to pending.
- `run_next(server_id)` runs one pending item for that server through `TransferRunner`.
- `recover_pending()` returns persisted unfinished tasks after constructing a new scheduler.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_queue.py -v
```

Expected:

```text
ModuleNotFoundError: No module named 'filezall_core.queue'
```

- [ ] **Step 3: Implement queue scheduler**

Create `src/filezall_core/queue.py` with:

- `TransferQueue(repository, runner, client_factory)`
- `add_task(task, items)`
- `list_items(status=None)`
- `pause_task(task_id)`
- `resume_task(task_id)`
- `cancel_task(task_id)`
- `retry_failed(task_id)`
- `run_next(server_id)`
- `recover_pending()`

Keep execution single-item and deterministic in M3. Parallel execution is deferred.

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/core/test_queue.py -v
```

Expected:

```text
All queue tests pass.
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_core/queue.py tests/core/test_queue.py
git commit -m "feat: add persistent transfer queue"
```

## Task 7: Desktop Transfer Center Actions

**Files:**
- Modify: `src/filezall_desktop/widgets.py`
- Modify: `src/filezall_desktop/main_window.py`
- Modify: `src/filezall_desktop/controller.py`
- Modify: `tests/desktop/test_main_window.py`
- Modify: `tests/desktop/test_controller.py`

- [ ] **Step 1: Write failing desktop tests**

Add tests covering:

- Transfer center renders queued item rows.
- Pause, resume, cancel, and retry buttons call controller queue actions.
- Controller delegates queue action calls to an injected queue service.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/desktop/test_main_window.py tests/desktop/test_controller.py -v
```

Expected:

```text
AttributeError for missing queue action controls.
```

- [ ] **Step 3: Implement desktop queue wiring**

Implementation requirements:

- Add queue buttons near transfer table.
- Add `set_transfer_items(items)` on `MainWindow`.
- Add controller methods: `pause_transfer`, `resume_transfer`, `cancel_transfer`, `retry_transfer`.
- Do not run transfers on the UI thread in M3 tests; controller only delegates queue actions.

- [ ] **Step 4: Run desktop tests to verify they pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/desktop/test_main_window.py tests/desktop/test_controller.py -v
```

Expected:

```text
All desktop tests pass.
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/filezall_desktop tests/desktop
git commit -m "feat: wire desktop transfer queue actions"
```

## Task 8: Full M3 Verification

**Files:**
- Verify all M3 files.

- [ ] **Step 1: Run all tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

Expected:

```text
All non-live tests pass; optional live SFTP test is skipped unless configured.
```

- [ ] **Step 2: Run GUI smoke test**

Run:

```powershell
$env:FILEZALL_HOME = (Join-Path (Get-Location) '.filezall-smoke'); .\.venv\Scripts\python.exe -c "from PySide6.QtCore import QTimer; from PySide6.QtWidgets import QApplication; from filezall_desktop.app import create_main_window; app = QApplication([]); window = create_main_window(); window.show(); QTimer.singleShot(100, app.quit); raise SystemExit(app.exec())"
```

Expected:

```text
Exit code 0.
```

- [ ] **Step 3: Check working tree**

Run:

```powershell
git status --short
```

Expected:

```text
No output.
```

## Self-Review

- Spec coverage: This plan covers M3 queue persistence, queue actions, file-level resume, task-level recovery, and desktop transfer-center controls.
- Out of scope: FTP/FTPS, Agent HTTP chunking, true background workers, multi-server parallel execution, process monitoring, and installers remain for later milestones.
- Placeholder scan: No placeholders; implementation tasks name concrete files, tests, commands, and expected results.
- Type consistency: `TransferTask`, `TransferItem`, `TransferRepository`, `TransferRunner`, and `TransferQueue` are introduced before desktop usage.
- Verification: M3 can be verified without a real SFTP server via fake protocol clients; live SFTP remains optional.
