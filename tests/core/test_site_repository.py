from pathlib import Path, PurePosixPath

from filezall_core.models import AuthMode, Protocol, SiteProfile
from filezall_core.site_repository import SiteRepository
from filezall_core.storage import initialize_database


def test_site_repository_saves_and_loads_profile(tmp_path: Path) -> None:
    database = tmp_path / "filezall.sqlite3"
    initialize_database(database)
    repository = SiteRepository(database)
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
        default_remote_path=PurePosixPath("/home/deploy"),
        default_local_path=tmp_path,
        credential_ref="cred-site-1",
    )

    repository.save(site)

    assert repository.get("site-1") == site


def test_site_repository_lists_profiles_ordered_by_name(tmp_path: Path) -> None:
    database = tmp_path / "filezall.sqlite3"
    initialize_database(database)
    repository = SiteRepository(database)

    repository.save(
        SiteProfile(
            id="b",
            name="Beta",
            host="beta.example.com",
            port=22,
            protocol=Protocol.SFTP,
            username="deploy",
            auth_mode=AuthMode.SSH_KEY,
            ssh_key_path=Path("C:/keys/beta.pem"),
        )
    )
    repository.save(
        SiteProfile(
            id="a",
            name="Alpha",
            host="alpha.example.com",
            port=22,
            protocol=Protocol.SFTP,
            username="deploy",
            auth_mode=AuthMode.PASSWORD,
        )
    )

    assert [site.name for site in repository.list()] == ["Alpha", "Beta"]


def test_site_repository_persists_group_name(tmp_path: Path) -> None:
    database = tmp_path / "filezall.sqlite3"
    initialize_database(database)
    repository = SiteRepository(database)
    site = SiteProfile(
        id="site-1",
        name="Production API",
        host="api.example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
        group_name="Production",
    )

    repository.save(site)

    assert repository.list()[0].group_name == "Production"


def test_site_repository_deletes_profile(tmp_path: Path) -> None:
    database = tmp_path / "filezall.sqlite3"
    initialize_database(database)
    repository = SiteRepository(database)
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
    )
    repository.save(site)

    repository.delete("site-1")

    assert repository.get("site-1") is None
