from __future__ import annotations

from filezall_core.ftp_adapter import FtpAdapter
from filezall_core.models import Protocol
from filezall_core.protocols import RemoteConnectionError, RemoteFileClient
from filezall_core.sftp_adapter import SftpAdapter


def create_remote_client(protocol: Protocol) -> RemoteFileClient:
    if protocol is Protocol.SFTP:
        return SftpAdapter()
    if protocol in {Protocol.FTP, Protocol.FTPS}:
        return FtpAdapter(protocol=protocol)
    raise RemoteConnectionError("Agent HTTP is not available until M6")
