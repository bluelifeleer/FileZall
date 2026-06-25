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
    with pytest.raises(RemoteConnectionError, match="Agent HTTP requires an Agent client factory"):
        create_remote_client(Protocol.AGENT_HTTP)


def test_client_factory_uses_injected_agent_http_factory() -> None:
    agent_client = object()

    assert (
        create_remote_client(
            Protocol.AGENT_HTTP,
            agent_client_factory=lambda: agent_client,
        )
        is agent_client
    )
