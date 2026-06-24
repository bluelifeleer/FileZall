from pathlib import Path

from filezall_core.app_paths import AppPaths, resolve_app_paths


def test_resolve_app_paths_uses_filezall_home_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FILEZALL_HOME", str(tmp_path))

    paths = resolve_app_paths()

    assert paths == AppPaths(
        root=tmp_path,
        database=tmp_path / "filezall.sqlite3",
        logs=tmp_path / "logs",
        downloads=tmp_path / "downloads",
    )


def test_app_paths_can_create_directories(tmp_path: Path) -> None:
    paths = AppPaths(
        root=tmp_path,
        database=tmp_path / "filezall.sqlite3",
        logs=tmp_path / "logs",
        downloads=tmp_path / "downloads",
    )

    paths.ensure_directories()

    assert paths.root.is_dir()
    assert paths.logs.is_dir()
    assert paths.downloads.is_dir()
