from __future__ import annotations

from collections.abc import Callable
from typing import Protocol as TypingProtocol

from filezall_core.models import RemoteFileEntry, SiteProfile


class ManagedSession(TypingProtocol):
    site: SiteProfile

    def connect_and_list_default(self, password: str | None = None) -> list[RemoteFileEntry]:
        ...

    def close(self) -> None:
        ...


class SessionManager:
    def __init__(self, session_factory: Callable[[SiteProfile], ManagedSession]) -> None:
        self._session_factory = session_factory
        self._sessions: dict[str, ManagedSession] = {}
        self._active_site_id: str | None = None

    def connect(self, site: SiteProfile, password: str | None = None) -> list[RemoteFileEntry]:
        session = self._session_factory(site)
        entries = session.connect_and_list_default(password=password)
        self._sessions[site.id] = session
        self._active_site_id = site.id
        return entries

    def get(self, site_id: str) -> ManagedSession | None:
        return self._sessions.get(site_id)

    def active(self) -> ManagedSession | None:
        if self._active_site_id is None:
            return None
        return self._sessions.get(self._active_site_id)

    def switch(self, site_id: str) -> ManagedSession:
        session = self._sessions[site_id]
        self._active_site_id = site_id
        return session

    def list_site_ids(self) -> list[str]:
        return list(self._sessions)

    def disconnect(self, site_id: str) -> None:
        session = self._sessions.pop(site_id)
        session.close()
        if self._active_site_id == site_id:
            self._active_site_id = next(iter(self._sessions), None)

    def disconnect_all(self) -> None:
        for site_id in list(self._sessions):
            self.disconnect(site_id)
