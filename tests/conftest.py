"""Shared test defaults for scenarios that exercise bundled card integrations."""

import pytest


@pytest.fixture(autouse=True)
def enable_bundled_cards_for_legacy_scenarios(monkeypatch):
    """Existing integration tests opt in when they expect bundled cards installed."""
    monkeypatch.setenv("MOVIESYNC_AUTO_INSTALL_BUNDLED_CARDS", "1")
