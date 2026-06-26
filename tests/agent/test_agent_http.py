import json
import threading
from pathlib import Path
from urllib import error, request

from filezall_agent.config import AgentConfig
from filezall_agent.resources import AgentResourceService
from filezall_agent.server import create_server


def test_agent_http_server_requires_bearer_token(tmp_path: Path) -> None:
    server, base_url = _start_server(tmp_path)
    try:
        try:
            request.urlopen(f"{base_url}/health", timeout=5)
        except error.HTTPError as exc:
            assert exc.code == 401
        else:
            raise AssertionError("Expected unauthorized request to fail")
    finally:
        server.shutdown()
        server.server_close()


def test_agent_http_server_serves_files_chunks_and_resources(tmp_path: Path) -> None:
    server, base_url = _start_server(tmp_path)
    try:
        deploy_dir = tmp_path / "home" / "deploy"
        deploy_dir.mkdir(parents=True)
        (deploy_dir / "app.txt").write_bytes(b"hello")

        health = _json(base_url, "/health")
        assert health["ok"] is True
        assert health["version"] == "0.1.0"
        assert health["api_version"] == 1
        assert _json(base_url, "/files/size?path=%2Fhome%2Fdeploy%2Fapp.txt") == {
            "exists": True,
            "size": 5,
        }
        assert _json(base_url, "/files/list?path=%2Fhome%2Fdeploy")["entries"][0]["name"] == "app.txt"

        chunk_status = _json(
            base_url,
            "/transfers/t1/chunks/0?path=%2Fhome%2Fdeploy%2Fupload.bin",
            data=b"abcdef",
        )
        assert chunk_status == {"index": 0, "size": 6, "complete": True}
        assert _json(base_url, "/transfers/t1/chunks") == {
            "chunks": [{"index": 0, "size": 6, "complete": True}]
        }
        assert _json(
            base_url,
            "/transfers/t1/merge",
            data={"path": "/home/deploy/upload.bin", "total_size": 6},
        ) == {"ok": True}
        assert _bytes(base_url, "/download-chunk?path=%2Fhome%2Fdeploy%2Fupload.bin&offset=2&size=3") == b"cde"
        assert _json(
            base_url,
            "/files/rename",
            data={"source": "/home/deploy/upload.bin", "destination": "/home/deploy/renamed.bin"},
        ) == {"ok": True}
        assert _json(
            base_url,
            "/files/verify",
            data={
                "path": "/home/deploy/renamed.bin",
                "checksum": "sha256:bef57ec7f53a6d40beb640a780a639c83bc29ac8a9816f1fc6c5c6dcd93c4721",
            },
        ) == {"ok": True}
        assert "cpu" in _json(base_url, "/resources")
        assert "processes" in _json(base_url, "/processes")
        assert _json(base_url, "/processes/123")["pid"] == 123
    finally:
        server.shutdown()
        server.server_close()


def test_agent_http_server_serves_live_cpu_and_network_samples(tmp_path: Path) -> None:
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    net_dir = proc_root / "net"
    net_dir.mkdir()
    (proc_root / "stat").write_text("cpu  100 0 100 800 0 0 0 0 0 0\n", encoding="utf-8")
    (proc_root / "meminfo").write_text(
        "MemTotal: 1000 kB\nMemAvailable: 500 kB\n",
        encoding="utf-8",
    )
    (net_dir / "dev").write_text(_net_dev(rx=1000, tx=2000), encoding="utf-8")
    clock_values = iter([10.0, 12.0])
    resource_service = AgentResourceService(proc_root=proc_root, clock=lambda: next(clock_values))
    server, base_url = _start_server(tmp_path, resource_service=resource_service)
    try:
        (proc_root / "stat").write_text("cpu  150 0 150 900 0 0 0 0 0 0\n", encoding="utf-8")
        (net_dir / "dev").write_text(_net_dev(rx=3000, tx=7000), encoding="utf-8")

        resources = _json(base_url, "/resources")

        assert resources["cpu"]["percent"] == 50.0
        assert resources["network"] == {"rx_bytes_per_sec": 1000, "tx_bytes_per_sec": 2500}
    finally:
        server.shutdown()
        server.server_close()


def _start_server(root: Path, resource_service=None):
    server = create_server(
        AgentConfig(root=root, token="secret", host="127.0.0.1", port=0),
        resource_service=resource_service,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def _request(base_url: str, path: str, data=None):
    body = None
    if isinstance(data, dict):
        body = json.dumps(data).encode("utf-8")
    elif isinstance(data, bytes):
        body = data
    agent_request = request.Request(f"{base_url}{path}", data=body)
    agent_request.add_header("Authorization", "Bearer secret")
    return request.urlopen(agent_request, timeout=5)


def _json(base_url: str, path: str, data=None):
    return json.loads(_request(base_url, path, data).read().decode("utf-8"))


def _bytes(base_url: str, path: str) -> bytes:
    return _request(base_url, path).read()


def _net_dev(*, rx: int, tx: int) -> str:
    return f"""
Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
  eth0: {rx} 8 0 0 0 0 0 0 {tx} 9 0 0 0 0 0 0
"""
