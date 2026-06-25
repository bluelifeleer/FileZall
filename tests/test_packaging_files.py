from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_packaging_files_exist() -> None:
    for relative_path in [
        "packaging/filezall.spec",
        "packaging/windows/build.ps1",
        "packaging/windows/FileZall.iss",
        "packaging/macos/build.sh",
        "packaging/README.md",
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
    assert "Inno Setup" in inno
    assert "create-dmg" in macos_build
    assert "notarization" in readme
    assert "code signing" in readme
