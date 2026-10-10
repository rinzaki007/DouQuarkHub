"""Architecture regression tests for built-in single-file card independence."""
from __future__ import annotations

import pytest

from moviesync.app import create_app


BUILTIN_CARD_IDS = (
    "douban",
    "filename_recognition",
    "pansou",
    "quark",
    "telegram",
    "tmdb",
)


@pytest.mark.parametrize("card_id", BUILTIN_CARD_IDS)
def test_uninstalling_one_builtin_card_does_not_break_other_cards_or_platform(
    tmp_path, card_id
):
    """Every bundled card can be removed without taking the host or peers down."""
    app = create_app({"MOVIESYNC_DATA_DIR": str(tmp_path)}, start_scheduler=False)
    services = app.extensions["moviesync"]
    registry = services["card_registry"]
    manager = services["file_card_plugins"]

    # Quark cannot be removed while it is the selected default target. Clear the
    # selection first so this test measures card isolation, not the safety guard.
    if card_id == "quark":
        services["config"].set_default_storage_target_id("")

    for other_id in BUILTIN_CARD_IDS:
        assert registry.get(other_id) is not None, f"{other_id} should load independently"
        assert (tmp_path / "cards" / f"{other_id}.py").is_file()

    removed = manager.uninstall(f"{card_id}.py")

    assert removed["card_id"] == card_id
    assert registry.get(card_id) is None
    assert not (tmp_path / "cards" / f"{card_id}.py").exists()

    for other_id in BUILTIN_CARD_IDS:
        if other_id != card_id:
            assert registry.get(other_id) is not None, (
                f"removing {card_id} must not unregister {other_id}"
            )

    # A missing optional card must not prevent core card discovery or platform APIs.
    response = app.test_client().get("/api/cards")
    assert response.status_code == 200
    listed_ids = {item["id"] for item in response.get_json()["cards"]}
    assert card_id not in listed_ids
    assert set(BUILTIN_CARD_IDS) - {card_id} <= listed_ids


def test_all_bundled_card_implementations_are_single_file_factories():
    """Bundled implementations must expose the loader contract in their own file."""
    from pathlib import Path

    template_dir = Path(__file__).resolve().parents[1] / "card_templates"
    files = {path.stem: path for path in template_dir.glob("*.py") if path.name != "__init__.py"}

    assert set(BUILTIN_CARD_IDS) <= set(files)
    for card_id in BUILTIN_CARD_IDS:
        source = files[card_id].read_text(encoding="utf-8")
        assert "def create_card(context)" in source, (
            f"{card_id}.py must provide its own create_card(context) factory"
        )
        assert "from card_templates." not in source, (
            f"{card_id}.py must not import another bundled card implementation"
        )
