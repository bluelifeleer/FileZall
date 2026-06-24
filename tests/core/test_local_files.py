from pathlib import Path

from filezall_core.local_files import list_local_directory


def test_list_local_directory_returns_sorted_entries(tmp_path: Path) -> None:
    (tmp_path / "zeta.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "alpha").mkdir()

    entries = list_local_directory(tmp_path)

    assert [entry.name for entry in entries] == ["alpha", "zeta.txt"]
    assert entries[0].is_dir is True
    assert entries[1].size_bytes == 5


def test_list_local_directory_rejects_files(tmp_path: Path) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text("hello", encoding="utf-8")

    try:
        list_local_directory(file_path)
    except NotADirectoryError as exc:
        assert str(file_path) in str(exc)
    else:
        raise AssertionError("expected NotADirectoryError")
