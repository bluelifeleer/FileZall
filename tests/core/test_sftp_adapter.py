import io
from pathlib import Path, PurePosixPath

import pytest

from filezall_core.models import AuthMode, Protocol, SiteProfile
from filezall_core.protocols import RemoteConnectionError
from filezall_core.sftp_adapter import SftpAdapter


class FakeSftpAttributes:
    def __init__(self, filename: str, st_mode: int, st_size: int, st_mtime: int) -> None:
        self.filename = filename
        self.st_mode = st_mode
        self.st_size = st_size
        self.st_mtime = st_mtime


class NonClosingBytesIO(io.BytesIO):
    def close(self) -> None:
        pass


class FakeSftpClient:
    def __init__(self) -> None:
        self.listdir_path = None
        self.put_calls = []
        self.get_calls = []
        self.stat_sizes = {}
        self.open_calls = []
        self.renames = []
        self.remote_files = {}
        self.closed = False

    def normalize(self, path: str) -> str:
        return "/home/deploy" if path == "." else path

    def listdir_attr(self, path: str):
        self.listdir_path = path
        return [FakeSftpAttributes("app.log", 0o100644, 42, 1_700_000_000)]

    def put(self, local_path: str, remote_path: str) -> None:
        self.put_calls.append((local_path, remote_path))

    def get(self, remote_path: str, local_path: str) -> None:
        self.get_calls.append((remote_path, local_path))

    def stat(self, path: str):
        if path not in self.stat_sizes:
            raise FileNotFoundError(path)
        return type("StatResult", (), {"st_size": self.stat_sizes[path]})()

    def open(self, path: str, mode: str):
        self.open_calls.append((path, mode))
        if "r" in mode:
            return NonClosingBytesIO(self.remote_files[path])
        handle = NonClosingBytesIO()
        self.remote_files[path] = handle
        return handle

    def rename(self, source_path: str, destination_path: str) -> None:
        self.renames.append((source_path, destination_path))

    def close(self) -> None:
        self.closed = True


class FakeSSHClient:
    def __init__(self) -> None:
        self.connect_kwargs = None
        self.sftp = FakeSftpClient()
        self.closed = False
        self.exec_commands = []
        self.exec_status = 0
        self.exec_stdout = b"{}"
        self.exec_stderr = b""

    def set_missing_host_key_policy(self, policy) -> None:
        self.policy = policy

    def connect(self, **kwargs) -> None:
        self.connect_kwargs = kwargs

    def open_sftp(self) -> FakeSftpClient:
        return self.sftp

    def exec_command(self, command: str):
        self.exec_commands.append(command)
        stdout = NonClosingBytesIO(self.exec_stdout)
        stderr = NonClosingBytesIO(self.exec_stderr)
        stdout.channel = type(
            "Channel",
            (),
            {"recv_exit_status": lambda _self: self.exec_status},
        )()
        return None, stdout, stderr

    def close(self) -> None:
        self.closed = True


class FakeParamiko:
    AutoAddPolicy = object

    def __init__(self) -> None:
        self.client = FakeSSHClient()

    def SSHClient(self) -> FakeSSHClient:
        return self.client


def test_sftp_adapter_connects_with_password() -> None:
    fake_paramiko = FakeParamiko()
    adapter = SftpAdapter(paramiko_module=fake_paramiko)
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )

    adapter.connect(site, password="secret")

    assert fake_paramiko.client.connect_kwargs["hostname"] == "example.com"
    assert fake_paramiko.client.connect_kwargs["username"] == "deploy"
    assert fake_paramiko.client.connect_kwargs["password"] == "secret"


def test_sftp_adapter_connects_with_ssh_key_and_passphrase() -> None:
    fake_paramiko = FakeParamiko()
    adapter = SftpAdapter(paramiko_module=fake_paramiko)
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.SSH_KEY,
        ssh_key_path=Path("C:/keys/deploy.pem"),
    )

    adapter.connect(site, password="key-passphrase")

    assert fake_paramiko.client.connect_kwargs["key_filename"] == str(Path("C:/keys/deploy.pem"))
    assert fake_paramiko.client.connect_kwargs["passphrase"] == "key-passphrase"
    assert "password" not in fake_paramiko.client.connect_kwargs


def test_sftp_adapter_rejects_ssh_key_auth_without_key_path() -> None:
    adapter = SftpAdapter(paramiko_module=FakeParamiko())
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.SSH_KEY,
    )

    with pytest.raises(RemoteConnectionError, match="SSH key path is required"):
        adapter.connect(site)


def test_sftp_adapter_lists_uploads_and_downloads(tmp_path: Path) -> None:
    fake_paramiko = FakeParamiko()
    adapter = SftpAdapter(paramiko_module=fake_paramiko)
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )
    adapter.connect(site, password="secret")

    entries = adapter.list_directory(PurePosixPath("/home/deploy"))
    adapter.upload_file(tmp_path / "local.txt", PurePosixPath("/home/deploy/local.txt"))
    adapter.download_file(PurePosixPath("/home/deploy/app.log"), tmp_path / "app.log")

    assert entries[0].name == "app.log"
    assert entries[0].size_bytes == 42
    assert fake_paramiko.client.sftp.put_calls == [
        (str(tmp_path / "local.txt"), "/home/deploy/local.txt")
    ]
    assert fake_paramiko.client.sftp.get_calls == [
        ("/home/deploy/app.log", str(tmp_path / "app.log"))
    ]


def test_sftp_adapter_reports_remote_size_or_none() -> None:
    fake_paramiko = FakeParamiko()
    adapter = SftpAdapter(paramiko_module=fake_paramiko)
    adapter._sftp = fake_paramiko.client.sftp
    fake_paramiko.client.sftp.stat_sizes["/home/deploy/.filezall.app.zip.part"] = 3

    assert adapter.remote_size(PurePosixPath("/home/deploy/.filezall.app.zip.part")) == 3
    assert adapter.remote_size(PurePosixPath("/home/deploy/missing.part")) is None


def test_sftp_adapter_upload_file_range_appends_from_offset(tmp_path: Path) -> None:
    fake_paramiko = FakeParamiko()
    adapter = SftpAdapter(paramiko_module=fake_paramiko)
    adapter._sftp = fake_paramiko.client.sftp
    local_file = tmp_path / "app.zip"
    local_file.write_bytes(b"abcdef")

    adapter.upload_file_range(
        local_file,
        PurePosixPath("/home/deploy/.filezall.app.zip.part"),
        offset=3,
    )

    handle = fake_paramiko.client.sftp.remote_files["/home/deploy/.filezall.app.zip.part"]
    assert fake_paramiko.client.sftp.open_calls == [
        ("/home/deploy/.filezall.app.zip.part", "ab")
    ]
    assert handle.getvalue() == b"def"


def test_sftp_adapter_download_file_range_appends_from_offset(tmp_path: Path) -> None:
    fake_paramiko = FakeParamiko()
    adapter = SftpAdapter(paramiko_module=fake_paramiko)
    adapter._sftp = fake_paramiko.client.sftp
    fake_paramiko.client.sftp.remote_files["/home/deploy/app.zip"] = b"abcdef"
    local_part = tmp_path / ".filezall.app.zip.part"
    local_part.write_bytes(b"ab")

    adapter.download_file_range(
        PurePosixPath("/home/deploy/app.zip"),
        local_part,
        offset=2,
    )

    assert fake_paramiko.client.sftp.open_calls == [("/home/deploy/app.zip", "rb")]
    assert local_part.read_bytes() == b"abcdef"


def test_sftp_adapter_renames_remote_path() -> None:
    fake_paramiko = FakeParamiko()
    adapter = SftpAdapter(paramiko_module=fake_paramiko)
    adapter._sftp = fake_paramiko.client.sftp

    adapter.rename(
        PurePosixPath("/home/deploy/.filezall.app.zip.part"),
        PurePosixPath("/home/deploy/app.zip"),
    )

    assert fake_paramiko.client.sftp.renames == [
        ("/home/deploy/.filezall.app.zip.part", "/home/deploy/app.zip")
    ]


def test_sftp_adapter_captures_command_output_over_existing_ssh() -> None:
    fake_paramiko = FakeParamiko()
    fake_paramiko.client.exec_stdout = b'{"ok": true}'
    adapter = SftpAdapter(paramiko_module=fake_paramiko)
    adapter._ssh = fake_paramiko.client
    adapter._sftp = fake_paramiko.client.sftp

    output = adapter.capture("python3 -c 'print(1)'")

    assert output == '{"ok": true}'
    assert fake_paramiko.client.exec_commands == ["python3 -c 'print(1)'"]
