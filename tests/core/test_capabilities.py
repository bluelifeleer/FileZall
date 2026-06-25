from filezall_core.capabilities import resource_monitoring_message
from filezall_core.models import Protocol


def test_resource_monitoring_message_for_sftp() -> None:
    assert resource_monitoring_message(Protocol.SFTP) == "Basic monitoring available through SSH."


def test_resource_monitoring_message_for_ftp_and_ftps() -> None:
    assert resource_monitoring_message(Protocol.FTP) == "Resource monitoring requires SSH or FileZall Agent."
    assert resource_monitoring_message(Protocol.FTPS) == "Resource monitoring requires SSH or FileZall Agent."
