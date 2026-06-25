from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from filezall_core.app_paths import resolve_app_paths
from filezall_core.credentials import CredentialService
from filezall_core.queue import TransferQueue
from filezall_core.site_repository import SiteRepository
from filezall_core.sftp_adapter import SftpAdapter
from filezall_core.storage import initialize_database
from filezall_core.transfer_repository import TransferRepository
from filezall_core.transfer_runner import TransferRunner
from filezall_desktop.main_window import MainWindow


def create_main_window() -> MainWindow:
    paths = resolve_app_paths()
    paths.ensure_directories()
    initialize_database(paths.database)
    transfer_repository = TransferRepository(paths.database)
    return MainWindow(
        site_repository=SiteRepository(paths.database),
        credential_service=CredentialService(),
        queue_service=TransferQueue(
            repository=transfer_repository,
            runner=TransferRunner(transfer_repository),
            client_factory=lambda _server_id: SftpAdapter(),
        ),
    )


def main() -> int:
    app = QApplication(sys.argv)
    window = create_main_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
