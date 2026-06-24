import os
from pathlib import PurePosixPath

import pytest

from filezall_core.models import AuthMode, Protocol, SiteProfile
from filezall_core.sftp_adapter import SftpAdapter


def _missing_live_sftp_env() -> list[str]:
    required = [
        "FILEZALL_SFTP_HOST",
        "FILEZALL_SFTP_USERNAME",
        "FILEZALL_SFTP_PASSWORD",
    ]
    return [name for name in required if not os.environ.get(name)]


@pytest.mark.skipif(
    bool(_missing_live_sftp_env()),
    reason="FILEZALL_SFTP_HOST, FILEZALL_SFTP_USERNAME, and FILEZALL_SFTP_PASSWORD are required",
)
def test_live_sftp_lists_home_directory() -> None:
    site = SiteProfile(
        id="live",
        name="Live",
        host=os.environ["FILEZALL_SFTP_HOST"],
        port=int(os.environ.get("FILEZALL_SFTP_PORT", "22")),
        protocol=Protocol.SFTP,
        username=os.environ["FILEZALL_SFTP_USERNAME"],
        auth_mode=AuthMode.PASSWORD,
    )
    adapter = SftpAdapter()
    try:
        adapter.connect(site, password=os.environ["FILEZALL_SFTP_PASSWORD"])
        home = adapter.home_directory()
        entries = adapter.list_directory(home)
    finally:
        adapter.close()

    assert isinstance(home, PurePosixPath)
    assert isinstance(entries, list)
