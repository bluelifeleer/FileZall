from pathlib import Path, PurePosixPath

from filezall_core.ftp_adapter import FtpAdapter
from filezall_core.models import AuthMode, Protocol, SiteProfile


class FakeFtp:
    def __init__(self) -> None:
        self.connected = None
        self.login_call = None
        self.cwd_path = "/home/deploy"
        self.prot_p_called = False
        self.stores = []
        self.retrieves = []
        self.renames = []
        self.closed = False
        self.size_map = {"/home/deploy/.filezall.app.zip.part": 3}
        self.entries = [
            ("app.log", {"type": "file", "size": "42", "modify": "20260625120000"}),
            ("public", {"type": "dir", "size": "0"}),
        ]

    def connect(self, host: str, port: int, timeout: int) -> None:
        self.connected = (host, port, timeout)

    def login(self, user: str, passwd: str | None) -> None:
        self.login_call = (user, passwd)

    def pwd(self) -> str:
        return self.cwd_path

    def mlsd(self, path: str):
        self.mlsd_path = path
        return self.entries

    def storbinary(self, command: str, fileobj, blocksize=8192, callback=None, rest=None) -> None:
        self.stores.append((command, fileobj.read(), rest))

    def retrbinary(self, command: str, callback, blocksize=8192, rest=None) -> None:
        self.retrieves.append((command, rest))
        callback(b"xyz")

    def size(self, path: str) -> int:
        if path not in self.size_map:
            raise FileNotFoundError(path)
        return self.size_map[path]

    def rename(self, source: str, destination: str) -> None:
        self.renames.append((source, destination))

    def quit(self) -> None:
        self.closed = True

    def prot_p(self) -> None:
        self.prot_p_called = True


class FakeFtps(FakeFtp):
    pass


class FakeFtpModule:
    def __init__(self) -> None:
        self.ftp = FakeFtp()
        self.ftps = FakeFtps()

    def FTP(self):
        return self.ftp

    def FTP_TLS(self):
        return self.ftps


def test_ftp_adapter_connects_lists_and_transfers(tmp_path: Path) -> None:
    module = FakeFtpModule()
    adapter = FtpAdapter(protocol=Protocol.FTP, ftp_module=module)
    local_file = tmp_path / "app.zip"
    local_file.write_bytes(b"abcdef")

    adapter.connect(_site(Protocol.FTP), password="secret")
    entries = adapter.list_directory(PurePosixPath("/home/deploy"))
    adapter.upload_file(local_file, PurePosixPath("/home/deploy/app.zip"))
    adapter.download_file(PurePosixPath("/home/deploy/app.zip"), tmp_path / "copy.zip")

    assert module.ftp.connected == ("example.com", 21, 15)
    assert module.ftp.login_call == ("deploy", "secret")
    assert [entry.name for entry in entries] == ["public", "app.log"]
    assert module.ftp.stores[0][0] == "STOR /home/deploy/app.zip"
    assert module.ftp.retrieves == [("RETR /home/deploy/app.zip", None)]
    assert (tmp_path / "copy.zip").read_bytes() == b"xyz"


def test_ftps_adapter_enables_protected_data_channel() -> None:
    module = FakeFtpModule()
    adapter = FtpAdapter(protocol=Protocol.FTPS, ftp_module=module)

    adapter.connect(_site(Protocol.FTPS), password="secret")

    assert module.ftps.prot_p_called is True


def test_ftp_adapter_supports_resume_operations(tmp_path: Path) -> None:
    module = FakeFtpModule()
    adapter = FtpAdapter(protocol=Protocol.FTP, ftp_module=module)
    adapter.connect(_site(Protocol.FTP), password="secret")
    local_file = tmp_path / "app.zip"
    local_file.write_bytes(b"abcdef")

    assert adapter.remote_size(PurePosixPath("/home/deploy/.filezall.app.zip.part")) == 3
    assert adapter.remote_size(PurePosixPath("/home/deploy/missing.part")) is None

    adapter.upload_file_range(
        local_file,
        PurePosixPath("/home/deploy/.filezall.app.zip.part"),
        offset=3,
    )
    adapter.download_file_range(PurePosixPath("/home/deploy/app.zip"), tmp_path / ".part", offset=2)
    adapter.rename(
        PurePosixPath("/home/deploy/.filezall.app.zip.part"),
        PurePosixPath("/home/deploy/app.zip"),
    )

    assert module.ftp.stores[-1] == ("STOR /home/deploy/.filezall.app.zip.part", b"def", 3)
    assert module.ftp.retrieves[-1] == ("RETR /home/deploy/app.zip", 2)
    assert (tmp_path / ".part").read_bytes() == b"xyz"
    assert module.ftp.renames == [
        ("/home/deploy/.filezall.app.zip.part", "/home/deploy/app.zip")
    ]


def _site(protocol: Protocol) -> SiteProfile:
    return SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=21,
        protocol=protocol,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )
