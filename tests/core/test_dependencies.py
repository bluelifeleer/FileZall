import importlib.util


def test_paramiko_is_available_for_sftp_adapter() -> None:
    assert importlib.util.find_spec("paramiko") is not None
