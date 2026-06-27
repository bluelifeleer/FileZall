from __future__ import annotations

import argparse
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from filezall_core.models import (
    AuthMode,
    Direction,
    LocalFileEntry,
    Protocol,
    RemoteFileEntry,
    SiteProfile,
    TransferItem,
    TransferStatus,
)
from filezall_core.performance import PerformanceBudget, measure_operation
from filezall_core.resource_models import CpuStats, DiskUsage, MemoryStats, NetworkStats, ProcessSummary, ResourceSnapshot
from filezall_desktop.controller import MainWindowController
from filezall_desktop.main_window import MainWindow


_APP: QApplication | None = None


class _SmokeController:
    def __init__(self) -> None:
        self.heartbeat_results: list[bool] = []

    def load_saved_sites(self) -> None:
        return None

    def heartbeat(self) -> bool:
        return self.heartbeat_results.pop(0) if self.heartbeat_results else True


class _RemoteSmokeSession:
    def __init__(self, path: PurePosixPath, entries: list[RemoteFileEntry]) -> None:
        self.current_remote_path = path
        self._entries = entries
        self.list_calls = 0

    def connect_and_list_default(self, password: str | None = None) -> list[RemoteFileEntry]:
        return list(self._entries)

    def list_directory(self, path: PurePosixPath) -> list[RemoteFileEntry]:
        self.list_calls += 1
        return list(self._entries)


def run_performance_smoke(
    *,
    directory_rows: int = 5_000,
    transfer_rows: int = 2_000,
    resource_samples: int = 120,
    log_rows: int = 5_000,
    remote_rows: int = 2_000,
    remote_samples: int = 50,
    heartbeat_samples: int = 50,
    directory_budget_ms: float = 1_500,
    transfer_budget_ms: float = 2_500,
    resource_budget_ms: float = 1_500,
    log_budget_ms: float = 1_500,
    remote_cache_budget_ms: float = 500,
    remote_force_budget_ms: float = 1_500,
    heartbeat_budget_ms: float = 500,
) -> dict:
    app = _ensure_app()
    smoke_controller = _SmokeController()
    window = MainWindow(controller=smoke_controller)
    try:
        directory_entries = _local_entries(directory_rows)
        directory_result = measure_operation(
            "large_directory",
            lambda: window.local_panel.set_entries(directory_entries),
        )
        app.processEvents()

        transfer_items = _transfer_items(transfer_rows)
        transfer_result = measure_operation(
            "large_transfer_queue",
            lambda: window.set_transfer_items(transfer_items),
        )
        app.processEvents()

        resource_snapshots = _resource_snapshots(resource_samples)
        resource_result = measure_operation(
            "repeated_resource_refresh",
            lambda: [window.set_resource_snapshot(snapshot) for snapshot in resource_snapshots],
        )
        app.processEvents()

        log_result = measure_operation(
            "long_log_stream",
            lambda: [window.append_log(f"Smoke transfer log row {index}") for index in range(log_rows)],
        )
        app.processEvents()

        remote_entries = _remote_entries(remote_rows, PurePosixPath("/srv/filezall-smoke"))
        remote_session = _RemoteSmokeSession(PurePosixPath("/srv/filezall-smoke"), remote_entries)
        remote_controller = MainWindowController(
            window=_SmokeController(),
            local_lister=lambda _path: [],
            session_factory=lambda _site: remote_session,
        )
        remote_controller.connect_for_window(
            SiteProfile(
                id="smoke-remote",
                name="Smoke Remote",
                host="127.0.0.1",
                port=22,
                protocol=Protocol.SFTP,
                username="smoke",
                auth_mode=AuthMode.PASSWORD,
                default_remote_path=PurePosixPath("/srv/filezall-smoke"),
            ),
            password="secret",
        )
        cached_before = remote_session.list_calls
        remote_cache_result = measure_operation(
            "remote_directory_cache",
            lambda: [
                remote_controller.load_remote_directory(PurePosixPath("/srv/filezall-smoke"))
                for _index in range(remote_samples)
            ],
        )
        cached_list_calls = remote_session.list_calls - cached_before
        forced_before = remote_session.list_calls
        remote_force_result = measure_operation(
            "remote_directory_forced_refresh",
            lambda: [
                remote_controller.load_remote_directory(
                    PurePosixPath("/srv/filezall-smoke"),
                    force_refresh=True,
                )
                for _index in range(remote_samples)
            ],
        )
        forced_list_calls = remote_session.list_calls - forced_before
        smoke_controller.heartbeat_results = [False] * heartbeat_samples
        heartbeat_result = measure_operation(
            "heartbeat_failure_diagnostics",
            lambda: _run_heartbeat_samples(window, app, heartbeat_samples),
        )
        app.processEvents()

        directory_check = PerformanceBudget(
            name="large_directory",
            max_elapsed_ms=directory_budget_ms,
        ).check(directory_result)
        transfer_check = PerformanceBudget(
            name="large_transfer_queue",
            max_elapsed_ms=transfer_budget_ms,
        ).check(transfer_result)
        resource_check = PerformanceBudget(
            name="repeated_resource_refresh",
            max_elapsed_ms=resource_budget_ms,
        ).check(resource_result)
        log_check = PerformanceBudget(
            name="long_log_stream",
            max_elapsed_ms=log_budget_ms,
        ).check(log_result)
        remote_cache_check = PerformanceBudget(
            name="remote_directory_cache",
            max_elapsed_ms=remote_cache_budget_ms,
        ).check(remote_cache_result)
        remote_force_check = PerformanceBudget(
            name="remote_directory_forced_refresh",
            max_elapsed_ms=remote_force_budget_ms,
        ).check(remote_force_result)
        heartbeat_check = PerformanceBudget(
            name="heartbeat_failure_diagnostics",
            max_elapsed_ms=heartbeat_budget_ms,
        ).check(heartbeat_result)
        scenarios = {
            "large_directory": _scenario_report(directory_check, directory_rows),
            "large_transfer_queue": _scenario_report(transfer_check, transfer_rows),
            "repeated_resource_refresh": _scenario_report(resource_check, resource_samples, size_key="samples"),
            "long_log_stream": _scenario_report(log_check, log_rows),
            "remote_directory_cache": _scenario_report(remote_cache_check, remote_samples, size_key="samples"),
            "remote_directory_forced_refresh": _scenario_report(
                remote_force_check,
                remote_samples,
                size_key="samples",
            ),
            "heartbeat_failure_diagnostics": _scenario_report(
                heartbeat_check,
                heartbeat_samples,
                size_key="samples",
            ),
        }
        return {
            "status": "passed" if all(item["passed"] for item in scenarios.values()) else "failed",
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "scenarios": scenarios,
            "diagnostic_state": window._diagnostic_state_snapshot(),
            "remote_directory": {
                "rows": remote_rows,
                "samples": remote_samples,
                "cached_list_calls": cached_list_calls,
                "forced_list_calls": forced_list_calls,
            },
        }
    finally:
        window.close()
        app.processEvents()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run FileZall desktop performance smoke checks.")
    parser.add_argument("--directory-rows", type=int, default=5_000)
    parser.add_argument("--transfer-rows", type=int, default=2_000)
    parser.add_argument("--resource-samples", type=int, default=120)
    parser.add_argument("--log-rows", type=int, default=5_000)
    parser.add_argument("--remote-rows", type=int, default=2_000)
    parser.add_argument("--remote-samples", type=int, default=50)
    parser.add_argument("--heartbeat-samples", type=int, default=50)
    parser.add_argument("--directory-budget-ms", type=float, default=1_500)
    parser.add_argument("--transfer-budget-ms", type=float, default=2_500)
    parser.add_argument("--resource-budget-ms", type=float, default=1_500)
    parser.add_argument("--log-budget-ms", type=float, default=1_500)
    parser.add_argument("--remote-cache-budget-ms", type=float, default=500)
    parser.add_argument("--remote-force-budget-ms", type=float, default=1_500)
    parser.add_argument("--heartbeat-budget-ms", type=float, default=500)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path, default=Path("performance-smoke.json"))
    args = parser.parse_args(argv)

    report = run_performance_smoke(
        directory_rows=args.directory_rows,
        transfer_rows=args.transfer_rows,
        resource_samples=args.resource_samples,
        log_rows=args.log_rows,
        remote_rows=args.remote_rows,
        remote_samples=args.remote_samples,
        heartbeat_samples=args.heartbeat_samples,
        directory_budget_ms=args.directory_budget_ms,
        transfer_budget_ms=args.transfer_budget_ms,
        resource_budget_ms=args.resource_budget_ms,
        log_budget_ms=args.log_budget_ms,
        remote_cache_budget_ms=args.remote_cache_budget_ms,
        remote_force_budget_ms=args.remote_force_budget_ms,
        heartbeat_budget_ms=args.heartbeat_budget_ms,
    )
    if args.baseline is not None:
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        report["baseline"] = {
            "path": str(args.baseline),
            "comparison": compare_performance_reports(report, baseline),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


def compare_performance_reports(
    current: dict,
    baseline: dict,
    *,
    tolerance_percent: float = 5.0,
) -> dict:
    scenarios = {}
    statuses = []
    baseline_scenarios = baseline.get("scenarios", {})
    for name, current_scenario in current.get("scenarios", {}).items():
        baseline_scenario = baseline_scenarios.get(name)
        if baseline_scenario is None:
            scenarios[name] = {"status": "new"}
            statuses.append("new")
            continue
        current_ms = float(current_scenario.get("elapsed_ms", 0.0))
        baseline_ms = float(baseline_scenario.get("elapsed_ms", 0.0))
        delta_ms = current_ms - baseline_ms
        delta_percent = (delta_ms / baseline_ms * 100) if baseline_ms else 0.0
        status = _comparison_status(delta_percent, tolerance_percent)
        scenarios[name] = {
            "status": status,
            "baseline_ms": baseline_ms,
            "current_ms": current_ms,
            "delta_ms": delta_ms,
            "delta_percent": delta_percent,
        }
        statuses.append(status)
    return {
        "status": _overall_comparison_status(statuses),
        "tolerance_percent": tolerance_percent,
        "scenarios": scenarios,
    }


def _ensure_app() -> QApplication:
    global _APP
    app = QApplication.instance()
    if app is not None:
        return app
    _APP = QApplication([])
    return _APP


def _run_heartbeat_samples(window: MainWindow, app: QApplication, samples: int) -> None:
    for _index in range(samples):
        window._handle_heartbeat_tick()
        deadline = time.monotonic() + 2.0
        while window._heartbeat_running and time.monotonic() < deadline:
            app.processEvents()
        if window._heartbeat_running:
            raise TimeoutError("heartbeat smoke sample did not finish")


def _local_entries(count: int) -> list[LocalFileEntry]:
    now = datetime.now(UTC)
    return [
        LocalFileEntry(
            path=Path("C:/filezall-smoke") / f"item-{index}.txt",
            name=f"item-{index}.txt",
            is_dir=index % 10 == 0,
            size_bytes=index * 17,
            modified_time=now,
        )
        for index in range(count)
    ]


def _transfer_items(count: int) -> list[TransferItem]:
    items = []
    for index in range(count):
        status = TransferStatus.RUNNING if index % 7 == 0 else TransferStatus.PENDING
        size = 10_000 + index
        transferred = min(size, index * 13) if status is TransferStatus.RUNNING else 0
        items.append(
            TransferItem(
                id=f"item-{index}",
                task_id=f"task-{index}",
                server_id=f"site-{index % 4}",
                direction=Direction.UPLOAD if index % 2 == 0 else Direction.DOWNLOAD,
                source_path=Path("C:/filezall-smoke") / f"item-{index}.bin",
                destination_path=PurePosixPath("/srv/filezall-smoke") / f"item-{index}.bin",
                temporary_path=PurePosixPath("/srv/filezall-smoke") / f".filezall.item-{index}.bin.part",
                size_bytes=size,
                protocol=Protocol.SFTP,
                bytes_transferred=transferred,
                status=status,
            )
        )
    return items


def _remote_entries(count: int, root: PurePosixPath) -> list[RemoteFileEntry]:
    now = datetime.now(UTC)
    return [
        RemoteFileEntry(
            path=root / f"remote-{index}.log",
            name=f"remote-{index}.log",
            is_dir=False,
            size_bytes=1_000 + index,
            modified_time=now,
        )
        for index in range(count)
    ]


def _resource_snapshots(count: int) -> list[ResourceSnapshot]:
    return [
        ResourceSnapshot(
            cpu=CpuStats(percent=float(index % 100)),
            memory=MemoryStats(
                total_bytes=16 * 1024 * 1024 * 1024,
                used_bytes=(4 * 1024 * 1024 * 1024) + index * 1024,
                available_bytes=(12 * 1024 * 1024 * 1024) - index * 1024,
            ),
            disks=[
                DiskUsage(
                    mount="/",
                    total_bytes=256 * 1024 * 1024 * 1024,
                    used_bytes=(80 * 1024 * 1024 * 1024) + index * 2048,
                    available_bytes=(176 * 1024 * 1024 * 1024) - index * 2048,
                )
            ],
            network=NetworkStats(
                rx_bytes_per_sec=1024 * (index + 1),
                tx_bytes_per_sec=2048 * (index + 1),
            ),
            processes=[
                ProcessSummary(
                    pid=1000 + process_index,
                    user="smoke",
                    name=f"process-{process_index}",
                    cpu_percent=float((index + process_index) % 100),
                    memory_percent=float(process_index % 20),
                )
                for process_index in range(20)
            ],
        )
        for index in range(count)
    ]


def _scenario_report(check, rows: int, *, size_key: str = "rows") -> dict:
    return {
        size_key: rows,
        "passed": check.passed,
        "elapsed_ms": check.elapsed_ms,
        "budget_ms": check.max_elapsed_ms,
        "message": check.message,
    }


def _comparison_status(delta_percent: float, tolerance_percent: float) -> str:
    if delta_percent > tolerance_percent:
        return "regressed"
    if delta_percent < -tolerance_percent:
        return "improved"
    return "unchanged"


def _overall_comparison_status(statuses: list[str]) -> str:
    if any(status == "regressed" for status in statuses):
        return "regressed"
    if statuses and all(status == "improved" for status in statuses):
        return "improved"
    return "unchanged"


if __name__ == "__main__":
    raise SystemExit(main())
