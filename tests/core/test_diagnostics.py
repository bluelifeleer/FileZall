import json
import zipfile

from filezall_core.diagnostics import DiagnosticPackageBuilder
from filezall_core.log_service import TransferLogService


def test_diagnostic_package_includes_manifest_session_logs_and_runtime_logs(tmp_path) -> None:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "filezall-runtime.log").write_text("runtime failure\n", encoding="utf-8")
    log_service = TransferLogService()
    log_service.append("Connected to Production")
    package_path = tmp_path / "diagnostics.zip"

    DiagnosticPackageBuilder(log_service=log_service, logs_dir=logs_dir).build(package_path)

    with zipfile.ZipFile(package_path) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        session_log = archive.read("logs/session.log").decode("utf-8")
        runtime_log = archive.read("logs/filezall-runtime.log").decode("utf-8")

    assert "manifest.json" in names
    assert manifest["app"] == "FileZall"
    assert manifest["version"] == "0.1.0"
    assert "Connected to Production" in session_log
    assert "runtime failure" in runtime_log


def test_diagnostic_package_includes_categorized_session_logs(tmp_path) -> None:
    log_service = TransferLogService()
    log_service.append_connection("Connected to Production")
    log_service.append_error("Connection failed")
    package_path = tmp_path / "diagnostics.zip"

    DiagnosticPackageBuilder(log_service=log_service).build(package_path)

    with zipfile.ZipFile(package_path) as archive:
        categorized = archive.read("logs/session-records.json").decode("utf-8")

    records = json.loads(categorized)
    assert records == [
        {
            "timestamp": log_service.records()[0].timestamp.isoformat(timespec="seconds"),
            "category": "connection",
            "level": "info",
            "message": "Connected to Production",
        },
        {
            "timestamp": log_service.records()[1].timestamp.isoformat(timespec="seconds"),
            "category": "error",
            "level": "error",
            "message": "Connection failed",
        },
    ]


def test_diagnostic_package_redacts_runtime_logs(tmp_path) -> None:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "filezall-runtime.log").write_text(
        "Authorization: Bearer live-token password=secret\n",
        encoding="utf-8",
    )
    package_path = tmp_path / "diagnostics.zip"

    DiagnosticPackageBuilder(
        log_service=TransferLogService(),
        logs_dir=logs_dir,
    ).build(package_path)

    with zipfile.ZipFile(package_path) as archive:
        runtime_log = archive.read("logs/filezall-runtime.log").decode("utf-8")

    assert "live-token" not in runtime_log
    assert "secret" not in runtime_log
    assert "Authorization: Bearer <redacted>" in runtime_log
    assert "password=<redacted>" in runtime_log
