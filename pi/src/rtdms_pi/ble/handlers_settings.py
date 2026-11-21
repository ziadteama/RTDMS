"""Apply already validated settings."""

from typing import Any

from ..settings import SettingsStore


def handle_settings(payload: dict[str, Any], settings: SettingsStore) -> None:
    settings.update(payload)
