import json

from filezall_desktop.performance_smoke import compare_performance_reports, main, run_performance_smoke


def test_performance_smoke_reports_large_directory_and_transfer_queue(qtbot) -> None:
    report = run_performance_smoke(
        directory_rows=8,
        transfer_rows=6,
        resource_samples=5,
        log_rows=7,
    )

    assert report["status"] == "passed"
    assert report["scenarios"]["large_directory"]["rows"] == 8
    assert report["scenarios"]["large_directory"]["elapsed_ms"] >= 0
    assert report["scenarios"]["large_directory"]["passed"] is True
    assert report["scenarios"]["large_transfer_queue"]["rows"] == 6
    assert report["scenarios"]["large_transfer_queue"]["elapsed_ms"] >= 0
    assert report["scenarios"]["large_transfer_queue"]["passed"] is True
    assert report["scenarios"]["repeated_resource_refresh"]["samples"] == 5
    assert report["scenarios"]["repeated_resource_refresh"]["elapsed_ms"] >= 0
    assert report["scenarios"]["repeated_resource_refresh"]["passed"] is True
    assert report["scenarios"]["long_log_stream"]["rows"] == 7
    assert report["scenarios"]["long_log_stream"]["elapsed_ms"] >= 0
    assert report["scenarios"]["long_log_stream"]["passed"] is True
    assert report["diagnostic_state"]["transfer_queue"]["total"] == 6
    assert report["diagnostic_state"]["logs"]["total_records"] == 7
    assert report["diagnostic_state"]["resource_refresh"]["chart_samples"] == 5


def test_performance_smoke_compares_report_to_baseline() -> None:
    baseline = {
        "scenarios": {
            "large_directory": {"elapsed_ms": 100.0},
            "large_transfer_queue": {"elapsed_ms": 200.0},
        }
    }
    current = {
        "scenarios": {
            "large_directory": {"elapsed_ms": 80.0},
            "large_transfer_queue": {"elapsed_ms": 250.0},
        }
    }

    comparison = compare_performance_reports(current, baseline)

    assert comparison["status"] == "regressed"
    assert comparison["scenarios"]["large_directory"]["status"] == "improved"
    assert comparison["scenarios"]["large_directory"]["delta_ms"] == -20.0
    assert comparison["scenarios"]["large_directory"]["delta_percent"] == -20.0
    assert comparison["scenarios"]["large_transfer_queue"]["status"] == "regressed"
    assert comparison["scenarios"]["large_transfer_queue"]["delta_ms"] == 50.0
    assert comparison["scenarios"]["large_transfer_queue"]["delta_percent"] == 25.0


def test_performance_smoke_cli_writes_baseline_comparison(qtbot, tmp_path) -> None:
    baseline_path = tmp_path / "baseline.json"
    output_path = tmp_path / "current.json"
    baseline_path.write_text(
        json.dumps(
            {
                "scenarios": {
                    "large_directory": {"elapsed_ms": 1000.0},
                    "large_transfer_queue": {"elapsed_ms": 1000.0},
                    "repeated_resource_refresh": {"elapsed_ms": 1000.0},
                    "long_log_stream": {"elapsed_ms": 1000.0},
                }
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "--directory-rows",
            "3",
            "--transfer-rows",
            "2",
            "--resource-samples",
            "2",
            "--log-rows",
            "2",
            "--baseline",
            str(baseline_path),
            "--output",
            str(output_path),
        ]
    )

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert report["baseline"]["path"] == str(baseline_path)
    assert set(report["baseline"]["comparison"]["scenarios"]) == {
        "large_directory",
        "large_transfer_queue",
        "repeated_resource_refresh",
        "long_log_stream",
    }
