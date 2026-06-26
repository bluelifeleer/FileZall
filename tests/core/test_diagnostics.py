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
