from __future__ import annotations

from filezall_core.models import Protocol


def resource_monitoring_message(protocol: Protocol) -> str:
    if protocol is Protocol.SFTP:
        return "Basic monitoring available through SSH."
    if protocol in {Protocol.FTP, Protocol.FTPS}:
        return "Resource monitoring requires SSH or FileZall Agent."
    if protocol is Protocol.AGENT_HTTP:
        return "Full monitoring available through FileZall Agent."
    return "Resource monitoring capability is unknown."
