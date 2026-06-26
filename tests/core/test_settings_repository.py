from pathlib import Path

from filezall_core.settings_repository import SettingsRepository
from filezall_core.storage import initialize_database


def test_settings_repository_persists_boolean_values(tmp_path: Path) -> None:
    database = tmp_path / "filezall.sqlite3"
    initialize_database(database)

    repository = SettingsRepository(database)

    assert repository.get_bool("onboarding.dismissed", default=False) is False

    repository.set_bool("onboarding.dismissed", True)

    reloaded = SettingsRepository(database)
    assert reloaded.get_bool("onboarding.dismissed", default=False) is True


def test_settings_repository_returns_default_for_missing_values(tmp_path: Path) -> None:
    database = tmp_path / "filezall.sqlite3"
    initialize_database(database)
    repository = SettingsRepository(database)

    assert repository.get("missing", default="fallback") == "fallback"
    assert repository.get_bool("missing-bool", default=True) is True
