from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from filezall_core.app_paths import resolve_app_paths
from filezall_core.credentials import CredentialService
from filezall_core.site_repository import SiteRepository
from filezall_core.storage import initialize_database
from filezall_desktop.main_window import MainWindow


def create_main_window() -> MainWindow:
    paths = resolve_app_paths()
    paths.ensure_directories()
    initialize_database(paths.database)
    return MainWindow(
        site_repository=SiteRepository(paths.database),
        credential_service=CredentialService(),
    )


def main() -> int:
    app = QApplication(sys.argv)
    window = create_main_window()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
