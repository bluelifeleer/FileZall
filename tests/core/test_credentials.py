from filezall_core.credentials import CredentialService


class FakeKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}
        self.deleted: list[tuple[str, str]] = []

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        self.deleted.append((service, username))
        self.values.pop((service, username), None)


def test_credential_service_stores_password_by_reference() -> None:
    backend = FakeKeyring()
    service = CredentialService(backend=backend)

    ref = service.save_secret("site-1", "password", "s3cret")

    assert ref == "site-1:password"
    assert service.get_secret(ref) == "s3cret"


def test_credential_service_deletes_secret() -> None:
    backend = FakeKeyring()
    service = CredentialService(backend=backend)
    ref = service.save_secret("site-1", "agent-token", "token")

    service.delete_secret(ref)

    assert service.get_secret(ref) is None
    assert backend.deleted == [("FileZall", "site-1:agent-token")]
