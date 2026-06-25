import pytest

from filezall_core.client_factory import create_remote_client
from filezall_core.ftp_adapter import FtpAdapter
from filezall_core.models import Protocol
from filezall_core.protocols import RemoteConnectionError
from filezall_core.sftp_adapter import SftpAdapter


def test_client_factory_creates_protocol_adapters() -> None:
    assert isinstance(create_remote_client(Protocol.SFTP), SftpAdapter)
    assert isinstance(create_remote_client(Protocol.FTP), FtpAdapter)
    assert isinstance(create_remote_client(Protocol.FTPS), FtpAdapter)


def test_client_factory_rejects_agent_http_until_m6() -> None:
    with pytest.raises(RemoteConnectionError, match="Agent HTTP is not available until M6"):
        create_remote_client(Protocol.AGENT_HTTP)
