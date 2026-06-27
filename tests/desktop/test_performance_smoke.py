from filezall_desktop.performance_smoke import run_performance_smoke


def test_performance_smoke_reports_large_directory_and_transfer_queue(qtbot) -> None:
    report = run_performance_smoke(directory_rows=8, transfer_rows=6)

    assert report["status"] == "passed"
    assert report["scenarios"]["large_directory"]["rows"] == 8
    assert report["scenarios"]["large_directory"]["elapsed_ms"] >= 0
    assert report["scenarios"]["large_directory"]["passed"] is True
    assert report["scenarios"]["large_transfer_queue"]["rows"] == 6
    assert report["scenarios"]["large_transfer_queue"]["elapsed_ms"] >= 0
    assert report["scenarios"]["large_transfer_queue"]["passed"] is True
    assert report["diagnostic_state"]["transfer_queue"]["total"] == 6
