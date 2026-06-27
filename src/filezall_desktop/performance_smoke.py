from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from filezall_core.models import Direction, LocalFileEntry, Protocol, TransferItem, TransferStatus
from filezall_core.performance import PerformanceBudget, measure_operation
from filezall_desktop.main_window import MainWindow


_APP: QApplication | None = None


class _SmokeController:
    def load_saved_sites(self) -> None:
        return None


def run_performance_smoke(
    *,
    directory_rows: int = 5_000,
    transfer_rows: int = 2_000,
    directory_budget_ms: float = 1_500,
    transfer_budget_ms: float = 2_500,
) -> dict:
    app = _ensure_app()
    window = MainWindow(controller=_SmokeController())
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

        directory_check = PerformanceBudget(
            name="large_directory",
            max_elapsed_ms=directory_budget_ms,
        ).check(directory_result)
        transfer_check = PerformanceBudget(
            name="large_transfer_queue",
            max_elapsed_ms=transfer_budget_ms,
        ).check(transfer_result)
        scenarios = {
            "large_directory": _scenario_report(directory_check, directory_rows),
            "large_transfer_queue": _scenario_report(transfer_check, transfer_rows),
        }
        return {
            "status": "passed" if all(item["passed"] for item in scenarios.values()) else "failed",
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "scenarios": scenarios,
            "diagnostic_state": window._diagnostic_state_snapshot(),
        }
    finally:
        window.close()
        app.processEvents()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run FileZall desktop performance smoke checks.")
    parser.add_argument("--directory-rows", type=int, default=5_000)
    parser.add_argument("--transfer-rows", type=int, default=2_000)
    parser.add_argument("--directory-budget-ms", type=float, default=1_500)
    parser.add_argument("--transfer-budget-ms", type=float, default=2_500)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--output", type=Path, default=Path("performance-smoke.json"))
    args = parser.parse_args(argv)

    report = run_performance_smoke(
        directory_rows=args.directory_rows,
        transfer_rows=args.transfer_rows,
        directory_budget_ms=args.directory_budget_ms,
        transfer_budget_ms=args.transfer_budget_ms,
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


def _scenario_report(check, rows: int) -> dict:
    return {
        "rows": rows,
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
