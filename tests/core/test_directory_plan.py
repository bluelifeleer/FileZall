from pathlib import Path, PurePosixPath

from filezall_core.directory_plan import plan_local_directory, plan_remote_directory
from filezall_core.models import Direction, RemoteFileEntry
from filezall_core.protocols import FakeRemoteClient


def test_plan_local_directory_returns_files_totals_and_relative_paths(tmp_path: Path) -> None:
    root = tmp_path / "site"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_bytes(b"hello")
    (root / "assets" / "app.js").write_bytes(b"abcdef")

    plan = plan_local_directory(root, PurePosixPath("/var/www"), direction=Direction.UPLOAD)

    assert plan.root == root
    assert plan.total_files == 2
    assert plan.total_bytes == 11
    assert [(item.relative_path, item.size_bytes) for item in plan.items] == [
        (PurePosixPath("assets/app.js"), 6),
        (PurePosixPath("index.html"), 5),
    ]
    assert plan.items[0].source_path == root / "assets" / "app.js"
    assert plan.items[0].destination_path == PurePosixPath("/var/www/assets/app.js")
    assert {item.direction for item in plan.items} == {Direction.UPLOAD}


def test_plan_remote_directory_walks_nested_entries() -> None:
    root = PurePosixPath("/home/deploy/site")
    client = FakeRemoteClient(
        entries={
            root: [
                RemoteFileEntry(root / "assets", "assets", True, 0, None),
                RemoteFileEntry(root / "index.html", "index.html", False, 5, None),
            ],
            root / "assets": [
                RemoteFileEntry(root / "assets" / "app.js", "app.js", False, 6, None),
            ],
        },
        home=PurePosixPath("/home/deploy"),
    )

    plan = plan_remote_directory(client, root, Path("C:/downloads/site"), direction=Direction.DOWNLOAD)

    assert plan.root == root
    assert plan.total_files == 2
    assert plan.total_bytes == 11
    assert [(item.relative_path, item.size_bytes) for item in plan.items] == [
        (PurePosixPath("assets/app.js"), 6),
        (PurePosixPath("index.html"), 5),
    ]
    assert plan.items[0].source_path == root / "assets" / "app.js"
    assert plan.items[0].destination_path == Path("C:/downloads/site/assets/app.js")
    assert {item.direction for item in plan.items} == {Direction.DOWNLOAD}
