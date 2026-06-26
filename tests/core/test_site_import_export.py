import json
from pathlib import Path, PurePosixPath

from filezall_core.models import AuthMode, Protocol, SiteProfile
from filezall_core.site_import_export import export_sites, import_sites


def test_export_sites_excludes_password_values(tmp_path: Path) -> None:
    export_path = tmp_path / "sites.json"
    site = SiteProfile(
        id="site-1",
        name="Production",
        host="example.com",
        port=22,
        protocol=Protocol.SFTP,
        username="deploy",
        auth_mode=AuthMode.PASSWORD,
        default_local_path=tmp_path,
        default_remote_path=PurePosixPath("/var/www"),
        credential_ref="credential-ref",
        ssh_key_path=Path("C:/keys/prod.pem"),
        agent_enabled=True,
        agent_token_ref="agent-token-ref",
        group_name="Production",
    )

    export_sites([site], export_path)

    payload = json.loads(export_path.read_text(encoding="utf-8"))
    exported = payload["sites"][0]
    assert "credential-ref" not in json.dumps(payload)
    assert exported["credential_ref"] is None
    assert exported["agent_token_ref"] == "agent-token-ref"
    assert exported["group_name"] == "Production"


def test_import_sites_clears_credential_references(tmp_path: Path) -> None:
    import_path = tmp_path / "sites.json"
    import_path.write_text(
        json.dumps(
            {
                "version": 1,
                "sites": [
                    {
                        "id": "site-1",
                        "name": "Production",
                        "host": "example.com",
                        "port": 22,
                        "protocol": "sftp",
                        "username": "deploy",
                        "auth_mode": "password",
                        "default_local_path": str(tmp_path),
                        "default_remote_path": "/var/www",
                        "credential_ref": "credential-ref",
                        "ssh_key_path": "C:/keys/prod.pem",
                        "agent_enabled": True,
                        "agent_token_ref": "agent-token-ref",
                        "group_name": "Production",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    sites = import_sites(import_path)

    assert sites == [
        SiteProfile(
            id="site-1",
            name="Production",
            host="example.com",
            port=22,
            protocol=Protocol.SFTP,
            username="deploy",
            auth_mode=AuthMode.PASSWORD,
            default_local_path=tmp_path,
            default_remote_path=PurePosixPath("/var/www"),
            credential_ref=None,
            ssh_key_path=Path("C:/keys/prod.pem"),
            agent_enabled=True,
            agent_token_ref=None,
            group_name="Production",
        )
    ]
