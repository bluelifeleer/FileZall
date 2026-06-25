from filezall_core.agent_tunnel import AgentTunnelManager
from filezall_core.models import AuthMode, Protocol, SiteProfile


class FakeTunnelHandle:
    def __init__(self, local_port: int) -> None:
        self.local_port = local_port
        self.stopped = False

    def is_running(self) -> bool:
        return not self.stopped

    def stop(self) -> None:
        self.stopped = True


class FakeTunnelRunner:
    def __init__(self, local_port: int = 49152) -> None:
        self.local_port = local_port
        self.commands: list[list[str]] = []

    def start(self, command: list[str]) -> FakeTunnelHandle:
        self.commands.append(command)
        return FakeTunnelHandle(self.local_port)


def _site() -> SiteProfile:
    return SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
        agent_enabled=True,
    )


def test_agent_tunnel_manager_opens_ssh_local_forward_and_returns_url() -> None:
    runner = FakeTunnelRunner(local_port=49200)
    manager = AgentTunnelManager(runner)

    endpoint = manager.open(_site(), local_port=0, remote_port=8765)

    assert endpoint.base_url == "http://127.0.0.1:49200"
    assert runner.commands == [
        [
            "ssh",
            "-N",
            "-L",
            "127.0.0.1:0:127.0.0.1:8765",
            "-p",
            "22",
            "deploy@example.com",
        ]
    ]
    assert manager.active() is True


def test_agent_tunnel_manager_closes_active_tunnel() -> None:
    runner = FakeTunnelRunner()
    manager = AgentTunnelManager(runner)

    manager.open(_site())
    manager.close()

    assert manager.active() is False
