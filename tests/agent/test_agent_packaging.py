from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_agent_packaging_files_exist() -> None:
    for relative_path in [
        "agent/systemd/filezall-agent.service",
        "agent/env/filezall-agent.env.example",
        "agent/build-package.ps1",
        "agent/build-package.sh",
    ]:
        assert (ROOT / relative_path).exists()


def test_agent_packaging_files_contain_required_release_commands() -> None:
    service = (ROOT / "agent/systemd/filezall-agent.service").read_text(encoding="utf-8")
    env = (ROOT / "agent/env/filezall-agent.env.example").read_text(encoding="utf-8")
    powershell = (ROOT / "agent/build-package.ps1").read_text(encoding="utf-8")
    shell = (ROOT / "agent/build-package.sh").read_text(encoding="utf-8")

    assert "filezall-agent" in service
    assert "systemd" in service
    assert "FILEZALL_AGENT_TOKEN" in env
    assert "tar" in powershell
    assert "tar" in shell
