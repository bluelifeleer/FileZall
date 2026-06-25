import json

from filezall_core.agent_client import AgentHttpClient


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class FakeOpener:
    def __init__(self) -> None:
        self.requests = []

    def open(self, request, timeout: int):
        self.requests.append((request, timeout))
        path = request.full_url.removeprefix("http://127.0.0.1:8765")
        payloads = {
            "/health": {"ok": True},
            "/resources": {
                "cpu": {"percent": 12.5},
                "memory": {"total_bytes": 1000, "used_bytes": 400, "available_bytes": 600},
                "disks": [
                    {"mount": "/", "total_bytes": 2000, "used_bytes": 1000, "available_bytes": 1000}
                ],
                "network": {"rx_bytes_per_sec": 10, "tx_bytes_per_sec": 20},
                "processes": [
                    {
                        "pid": 123,
                        "user": "deploy",
                        "name": "python",
                        "cpu_percent": 1.5,
                        "memory_percent": 2.5,
                    }
                ],
            },
            "/processes": {
                "processes": [
                    {
                        "pid": 123,
                        "user": "deploy",
                        "name": "python",
                        "cpu_percent": 1.5,
                        "memory_percent": 2.5,
                    }
                ]
            },
            "/processes/123": {
                "pid": 123,
                "user": "deploy",
                "name": "python",
                "cpu_percent": 1.5,
                "memory_percent": 2.5,
                "command_line": "python app.py",
                "start_time": "2026-06-25T12:00:00Z",
                "thread_count": 8,
                "status": "sleeping",
            },
        }
        return FakeResponse(payloads[path])


def test_agent_client_checks_health_and_sends_token() -> None:
    opener = FakeOpener()
    client = AgentHttpClient("http://127.0.0.1:8765", token="secret-token", opener=opener)

    assert client.health() is True

    request, timeout = opener.requests[0]
    assert timeout == 10
    assert request.get_header("Authorization") == "Bearer secret-token"


def test_agent_client_maps_resource_snapshot() -> None:
    client = AgentHttpClient("http://127.0.0.1:8765", token="secret-token", opener=FakeOpener())

    snapshot = client.resource_snapshot()

    assert snapshot.cpu.percent == 12.5
    assert snapshot.memory.available_bytes == 600
    assert snapshot.disks[0].mount == "/"
    assert snapshot.network.tx_bytes_per_sec == 20
    assert snapshot.processes[0].pid == 123


def test_agent_client_maps_process_list_and_detail() -> None:
    client = AgentHttpClient("http://127.0.0.1:8765", token="secret-token", opener=FakeOpener())

    processes = client.processes()
    detail = client.process_detail(123)

    assert processes[0].name == "python"
    assert detail.command_line == "python app.py"
    assert detail.thread_count == 8
