import json
from pathlib import Path, PurePosixPath

from filezall_core.agent_file_client import AgentHttpFileClient


class FakeResponse:
    def __init__(self, payload: dict | bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        if isinstance(self._payload, bytes):
            return self._payload
        return json.dumps(self._payload).encode("utf-8")


class FakeOpener:
    def __init__(self) -> None:
        self.requests = []

    def open(self, request, timeout: int):
        self.requests.append((request, request.data, timeout))
        url = request.full_url
        if "/files/list" in url:
            return FakeResponse(
                {
                    "entries": [
                        {
                            "path": "/home/deploy/app.log",
                            "name": "app.log",
                            "is_dir": False,
                            "size_bytes": 42,
                            "modified_time": None,
                        }
                    ]
                }
            )
        if "/files/walk" in url:
            return FakeResponse(
                {
                    "entries": [
                        {
                            "path": "/home/deploy/site/assets/app.js",
                            "name": "app.js",
                            "is_dir": False,
                            "size_bytes": 6,
                            "modified_time": None,
                        },
                        {
                            "path": "/home/deploy/site/index.html",
                            "name": "index.html",
                            "is_dir": False,
                            "size_bytes": 5,
                            "modified_time": None,
                        },
                    ]
                }
            )
        if "/files/size" in url:
            return FakeResponse({"exists": True, "size": 6})
        if "/download-chunk" in url:
            return FakeResponse(b"def")
        if (
            "/merge" in url
            or "/files/rename" in url
            or "/files/delete" in url
            or "/files/mkdir" in url
            or "/files/touch" in url
        ):
            return FakeResponse({"ok": True})
        return FakeResponse({"index": 1, "size": len(request.data or b""), "complete": True})


def test_agent_file_client_lists_and_reports_remote_size() -> None:
    opener = FakeOpener()
    client = AgentHttpFileClient("http://127.0.0.1:8765", token="secret", opener=opener)

    entries = client.list_directory(PurePosixPath("/home/deploy"))
    size = client.remote_size(PurePosixPath("/home/deploy/app.zip"))

    assert entries[0].name == "app.log"
    assert entries[0].size_bytes == 42
    assert size == 6


def test_agent_file_client_walks_directory_with_single_agent_request() -> None:
    opener = FakeOpener()
    client = AgentHttpFileClient("http://127.0.0.1:8765", token="secret", opener=opener)

    entries = client.walk_directory(PurePosixPath("/home/deploy/site"))

    assert [entry.path for entry in entries] == [
        PurePosixPath("/home/deploy/site/assets/app.js"),
        PurePosixPath("/home/deploy/site/index.html"),
    ]
    assert [
        request.full_url
        for request, _body, _timeout in opener.requests
        if "/files/walk" in request.full_url
    ] == ["http://127.0.0.1:8765/files/walk?path=%2Fhome%2Fdeploy%2Fsite"]


def test_agent_file_client_uploads_and_downloads_ranges(tmp_path: Path) -> None:
    opener = FakeOpener()
    client = AgentHttpFileClient(
        "http://127.0.0.1:8765",
        token="secret",
        opener=opener,
        chunk_size=3,
    )
    local_file = tmp_path / "app.zip"
    local_file.write_bytes(b"abcdef")
    local_part = tmp_path / ".filezall.app.zip.part"
    local_part.write_bytes(b"abc")

    client.upload_file_range(local_file, PurePosixPath("/home/deploy/.filezall.app.zip.part"), offset=3)
    client.download_file_range(PurePosixPath("/home/deploy/app.zip"), local_part, offset=3)

    upload_requests = [
        (request.full_url, body)
        for request, body, _timeout in opener.requests
        if "/chunks/" in request.full_url
    ]
    assert upload_requests[0][1] == b"def"
    assert local_part.read_bytes() == b"abcdef"


def test_agent_file_client_renames_remote_path() -> None:
    opener = FakeOpener()
    client = AgentHttpFileClient("http://127.0.0.1:8765", token="secret", opener=opener)

    client.rename(
        PurePosixPath("/home/deploy/.filezall.app.zip.part"),
        PurePosixPath("/home/deploy/app.zip"),
    )

    rename_request, body, _timeout = opener.requests[-1]
    assert rename_request.full_url.endswith("/files/rename")
    assert json.loads(body.decode("utf-8")) == {
        "source": "/home/deploy/.filezall.app.zip.part",
        "destination": "/home/deploy/app.zip",
    }


def test_agent_file_client_manages_remote_paths() -> None:
    opener = FakeOpener()
    client = AgentHttpFileClient("http://127.0.0.1:8765", token="secret", opener=opener)

    client.delete_path(PurePosixPath("/home/deploy/app.txt"), is_dir=False)
    client.delete_path(PurePosixPath("/home/deploy/old"), is_dir=True)
    client.make_directory(PurePosixPath("/home/deploy/new-dir"))
    client.create_file(PurePosixPath("/home/deploy/new.txt"))

    requests = [
        (request.full_url, json.loads(body.decode("utf-8")))
        for request, body, _timeout in opener.requests
    ]
    assert requests == [
        (
            "http://127.0.0.1:8765/files/delete",
            {"path": "/home/deploy/app.txt", "is_dir": False},
        ),
        (
            "http://127.0.0.1:8765/files/delete",
            {"path": "/home/deploy/old", "is_dir": True},
        ),
        ("http://127.0.0.1:8765/files/mkdir", {"path": "/home/deploy/new-dir"}),
        ("http://127.0.0.1:8765/files/touch", {"path": "/home/deploy/new.txt"}),
    ]
