from __future__ import annotations

import keyring


class CredentialService:
    def __init__(self, backend=keyring, service_name: str = "FileZall") -> None:
        self._backend = backend
        self._service_name = service_name

    def save_secret(self, site_id: str, purpose: str, secret: str) -> str:
        ref = f"{site_id}:{purpose}"
        self._backend.set_password(self._service_name, ref, secret)
        return ref

    def get_secret(self, ref: str | None) -> str | None:
        if not ref:
            return None
        return self._backend.get_password(self._service_name, ref)

    def delete_secret(self, ref: str | None) -> None:
        if not ref:
            return
        self._backend.delete_password(self._service_name, ref)
