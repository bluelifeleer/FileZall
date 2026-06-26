from __future__ import annotations

import faulthandler
import sys
import tempfile
import traceback
from pathlib import Path

from PySide6.QtWidgets import QApplication

from filezall_core.agent_deployment import (
    AgentDeploymentService,
    ParamikoAgentDeployRunner,
    build_agent_package,
)
from filezall_core.app_paths import resolve_app_paths
from filezall_core.credentials import CredentialService
from filezall_core.queue import TransferQueue
from filezall_core.site_repository import SiteRepository
from filezall_core.sftp_adapter import SftpAdapter
from filezall_core.storage import initialize_database
from filezall_core.transfer_repository import TransferRepository
from filezall_core.transfer_runner import TransferRunner
from filezall_desktop.main_window import MainWindow

_diagnostic_log_handle = None


def create_main_window() -> MainWindow:
    paths = resolve_app_paths()
    paths.ensure_directories()
    _enable_runtime_diagnostics(paths.logs)
    initialize_database(paths.database)
    transfer_repository = TransferRepository(paths.database)
    credential_service = CredentialService()
    site_repository = SiteRepository(paths.database)
    agent_root = _agent_root()
    return MainWindow(
        site_repository=site_repository,
        credential_service=credential_service,
        queue_service=TransferQueue(
            repository=transfer_repository,
            runner=TransferRunner(transfer_repository),
            client_factory=lambda _server_id: SftpAdapter(),
        ),
        agent_install_service=AgentDeploymentService(
            package_builder=lambda: build_agent_package(
                agent_root,
                Path(tempfile.gettempdir()) / "filezall-agent-package",
            ),
            runner_factory=lambda site, password: ParamikoAgentDeployRunner(site, password),
            credential_service=credential_service,
            site_repository=site_repository,
        ),
    )


def _enable_runtime_diagnostics(logs_dir: Path) -> None:
    global _diagnostic_log_handle
    if _diagnostic_log_handle is None or _diagnostic_log_handle.closed:
        _diagnostic_log_handle = (logs_dir / "filezall-runtime.log").open(
            "a",
            encoding="utf-8",
        )
    faulthandler.enable(file=_diagnostic_log_handle, all_threads=True)

    def _write_unhandled_exception(exc_type, exc_value, exc_traceback) -> None:
        traceback.print_exception(
            exc_type,
            exc_value,
            exc_traceback,
            file=_diagnostic_log_handle,
        )
        _diagnostic_log_handle.flush()
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = _write_unhandled_exception


def main() -> int:
    app = QApplication(sys.argv)
    window = create_main_window()
    window.show()
    return app.exec()


def _agent_root() -> Path:
    candidates = [
        Path(getattr(sys, "_MEIPASS", "")) / "agent",
        Path(sys.executable).resolve().parent / "_internal" / "agent",
        Path(__file__).resolve().parents[2] / "agent",
    ]
    for candidate in candidates:
        if (candidate / "filezall_agent").exists():
            return candidate
    return candidates[-1]


if __name__ == "__main__":
    raise SystemExit(main())
