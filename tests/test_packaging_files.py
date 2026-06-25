from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_packaging_files_exist() -> None:
    for relative_path in [
        "packaging/filezall.spec",
        "packaging/windows/build.ps1",
        "packaging/windows/FileZall.iss",
        "packaging/macos/build.sh",
        "packaging/README.md",
        "docs/agent-deployment.md",
        "scripts/validate-linux-agent.ps1",
    ]:
        assert (ROOT / relative_path).exists()


def test_packaging_files_contain_platform_build_commands() -> None:
    spec = (ROOT / "packaging/filezall.spec").read_text(encoding="utf-8")
    windows_build = (ROOT / "packaging/windows/build.ps1").read_text(encoding="utf-8")
    inno = (ROOT / "packaging/windows/FileZall.iss").read_text(encoding="utf-8")
    macos_build = (ROOT / "packaging/macos/build.sh").read_text(encoding="utf-8")
    readme = (ROOT / "packaging/README.md").read_text(encoding="utf-8")

    assert "filezall_desktop.app" in spec
    assert "pyinstaller" in windows_build
    assert ".venv" in windows_build
    assert "-m PyInstaller" in windows_build
    assert "Inno Setup" in inno
    assert "create-dmg" in macos_build
    assert "notarization" in readme
    assert "code signing" in readme
    assert "docs/agent-deployment.md" in readme


def test_windows_inno_app_id_is_valid_guid() -> None:
    inno = (ROOT / "packaging/windows/FileZall.iss").read_text(encoding="utf-8")
    match = re.search(r"^AppId=\{\{(?P<guid>[0-9A-Fa-f-]{36})\}$", inno, re.MULTILINE)

    assert match is not None
    assert re.fullmatch(
        r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}",
        match.group("guid"),
    )


def test_agent_deployment_docs_cover_install_tunnel_and_health_check() -> None:
    guide = (ROOT / "docs/agent-deployment.md").read_text(encoding="utf-8")

    assert "FILEZALL_AGENT_TOKEN" in guide
    assert "filezall-agent" in guide
    assert "systemctl" in guide
    assert "scripts/validate-linux-agent.ps1" in guide
    assert "ssh -L" in guide
    assert "health" in guide


def test_linux_agent_validation_script_covers_real_server_flow() -> None:
    script = (ROOT / "scripts/validate-linux-agent.ps1").read_text(encoding="utf-8")

    for required in [
        "FILEZALL_LINUX_HOST",
        "FILEZALL_LINUX_USER",
        "FILEZALL_LINUX_TOKEN",
        "agent\\build-package.ps1",
        "scp",
        "ssh -L",
        "systemctl",
        "/health",
        "/resources",
    ]:
        assert required in script
