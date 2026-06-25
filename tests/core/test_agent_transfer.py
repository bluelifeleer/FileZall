import json

from filezall_core.agent_transfer import AgentTransferClient, ChunkStatus


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
        body = request.data
        self.requests.append((request, body, timeout))
        url = request.full_url
        if "/download-chunk" in url:
            return FakeResponse(b"chunk-bytes")
        if url.endswith("/chunks"):
            return FakeResponse({"chunks": [{"index": 0, "size": 5, "complete": True}]})
        if url.endswith("/merge"):
            return FakeResponse({"ok": True})
        if url.endswith("/verify"):
            return FakeResponse({"ok": True})
        return FakeResponse({"index": 0, "size": len(body or b""), "complete": True})


def test_agent_transfer_uploads_and_downloads_chunks_with_token() -> None:
    opener = FakeOpener()
    client = AgentTransferClient("http://127.0.0.1:8765", token="secret", opener=opener)

    status = client.upload_chunk("/remote/app.zip", "transfer-1", index=0, data=b"hello")
    data = client.download_chunk("/remote/app.zip", offset=5, size=10)

    upload_request, upload_body, upload_timeout = opener.requests[0]
    download_request, _download_body, _download_timeout = opener.requests[1]
    assert status == ChunkStatus(index=0, size=5, complete=True)
    assert data == b"chunk-bytes"
    assert upload_body == b"hello"
    assert upload_timeout == 30
    assert upload_request.get_header("Authorization") == "Bearer secret"
    assert "path=%2Fremote%2Fapp.zip" in upload_request.full_url
    assert "offset=5" in download_request.full_url


def test_agent_transfer_queries_status_merges_and_verifies() -> None:
    opener = FakeOpener()
    client = AgentTransferClient("http://127.0.0.1:8765", token="secret", opener=opener)

    statuses = client.chunk_status("transfer-1")
    merged = client.merge("transfer-1", "/remote/app.zip", total_size=5)
    verified = client.verify("/remote/app.zip", checksum="sha256:abc")

    assert statuses == [ChunkStatus(index=0, size=5, complete=True)]
    assert merged is True
    assert verified is True
