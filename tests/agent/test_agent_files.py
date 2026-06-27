from pathlib import Path

from filezall_agent.config import AgentConfig
from filezall_agent.files import AgentFileService


def test_agent_file_service_lists_sizes_renames_and_verifies(tmp_path: Path) -> None:
    service = AgentFileService(AgentConfig(root=tmp_path, token="secret"))
    directory = tmp_path / "home" / "deploy"
    directory.mkdir(parents=True)
    file_path = directory / "app.txt"
    file_path.write_bytes(b"hello")

    entries = service.list_directory("/home/deploy")
    size = service.file_size("/home/deploy/app.txt")
    missing_size = service.file_size("/home/deploy/missing.txt")
    service.rename("/home/deploy/app.txt", "/home/deploy/renamed.txt")

    assert entries == [
        {
            "path": "/home/deploy/app.txt",
            "name": "app.txt",
            "is_dir": False,
            "size_bytes": 5,
            "modified_time": entries[0]["modified_time"],
        }
    ]
    assert size == {"exists": True, "size": 5}
    assert missing_size == {"exists": False, "size": 0}
    assert (directory / "renamed.txt").read_bytes() == b"hello"
    assert service.verify("/home/deploy/renamed.txt", "sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824") == {"ok": True}


def test_agent_file_service_walks_directory_tree_in_one_call(tmp_path: Path) -> None:
    service = AgentFileService(AgentConfig(root=tmp_path, token="secret"))
    directory = tmp_path / "home" / "deploy" / "site"
    assets = directory / "assets"
    assets.mkdir(parents=True)
    (directory / "index.html").write_bytes(b"hello")
    (assets / "app.js").write_bytes(b"abcdef")

    entries = service.walk_directory("/home/deploy/site")

    assert [entry["path"] for entry in entries] == [
        "/home/deploy/site/assets/app.js",
        "/home/deploy/site/index.html",
    ]
    assert [entry["size_bytes"] for entry in entries] == [6, 5]


def test_agent_file_service_deletes_and_creates_paths(tmp_path: Path) -> None:
    service = AgentFileService(AgentConfig(root=tmp_path, token="secret"))
    directory = tmp_path / "home" / "deploy"
    directory.mkdir(parents=True)
    file_path = directory / "app.txt"
    file_path.write_text("hello", encoding="utf-8")
    old_dir = directory / "old"
    old_dir.mkdir()

    assert service.delete_path("/home/deploy/app.txt", is_dir=False) == {"ok": True}
    assert service.delete_path("/home/deploy/old", is_dir=True) == {"ok": True}
    assert service.make_directory("/home/deploy/new-dir") == {"ok": True}
    assert service.create_file("/home/deploy/new.txt") == {"ok": True}

    assert not file_path.exists()
    assert not old_dir.exists()
    assert (directory / "new-dir").is_dir()
    assert (directory / "new.txt").read_bytes() == b""


def test_agent_file_service_writes_merges_and_downloads_chunks(tmp_path: Path) -> None:
    service = AgentFileService(AgentConfig(root=tmp_path, token="secret"))

    first = service.write_chunk("/home/deploy/app.bin", "transfer-1", index=0, data=b"abc")
    second = service.write_chunk("/home/deploy/app.bin", "transfer-1", index=1, data=b"def")
    statuses = service.chunk_status("transfer-1")
    merged = service.merge("transfer-1", "/home/deploy/app.bin", total_size=6)
    chunk = service.download_chunk("/home/deploy/app.bin", offset=2, size=3)

    assert first == {"index": 0, "size": 3, "complete": True}
    assert second == {"index": 1, "size": 3, "complete": True}
    assert statuses == {
        "chunks": [
            {"index": 0, "size": 3, "complete": True},
            {"index": 1, "size": 3, "complete": True},
        ]
    }
    assert merged == {"ok": True}
    assert (tmp_path / "home" / "deploy" / "app.bin").read_bytes() == b"abcdef"
    assert chunk == b"cde"


def test_agent_file_service_blocks_paths_outside_configured_root(tmp_path: Path) -> None:
    service = AgentFileService(AgentConfig(root=tmp_path, token="secret"))

    try:
        service.list_directory("/../../outside")
    except ValueError as exc:
        assert "outside agent root" in str(exc)
    else:
        raise AssertionError("Expected path escape to be rejected")
