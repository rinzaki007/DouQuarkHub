"""Regression tests for trusted, persistent single-file card plugins."""
from __future__ import annotations

import io
import logging
from pathlib import Path

import pytest

from moviesync.card_plugins import CardFilePluginManager
from moviesync.cards import CardRegistry


def _plugin_source(card_id: str = "upload-demo") -> bytes:
    return f'''from moviesync.cards import Card, CardManifest


class DemoCard(Card):
    manifest = CardManifest(id="{card_id}", name="Uploaded Demo", type="custom")


def create_card(context):
    return DemoCard()
'''.encode()


def test_file_plugin_loads_and_uninstall_removes_only_plugin_file(tmp_path):
    plugin_dir = tmp_path / "cards"
    plugin_dir.mkdir()
    (plugin_dir / "sample-plugin.py").write_bytes(_plugin_source("sample-plugin"))
    registry = CardRegistry()
    manager = CardFilePluginManager(plugin_dir, registry, logging.getLogger("test-card-plugins"))

    loaded = manager.load_all()

    assert loaded == ["sample-plugin"]
    assert registry.get("sample-plugin") is not None
    assert manager.list_plugins()[0]["loaded"] is True

    removed = manager.uninstall("sample-plugin.py")

    assert removed == {"filename": "sample-plugin.py", "card_id": "sample-plugin"}
    assert registry.get("sample-plugin") is None
    assert not (plugin_dir / "sample-plugin.py").exists()
    assert manager.list_plugins() == []


def test_file_plugin_requires_filename_to_match_manifest_id(tmp_path):
    manager = CardFilePluginManager(
        tmp_path / "cards", CardRegistry(), logging.getLogger("test-card-plugins")
    )
    with pytest.raises(ValueError, match="必须与文件名"):
        manager.install("sample-plugin.py", _plugin_source("different-id"))
    assert not (tmp_path / "cards" / "sample-plugin.py").exists()


@pytest.mark.parametrize("filename", ["../escape.py", "UPPER.py", "not-python.txt", ".hidden.py"])
def test_file_plugin_rejects_unsafe_filenames(tmp_path, filename):
    manager = CardFilePluginManager(
        tmp_path / "cards", CardRegistry(), logging.getLogger("test-card-plugins")
    )
    with pytest.raises(ValueError):
        manager.validate_filename(filename)


def test_file_plugin_install_rejects_oversized_source(tmp_path):
    manager = CardFilePluginManager(
        tmp_path / "cards", CardRegistry(), logging.getLogger("test-card-plugins")
    )
    with pytest.raises(ValueError, match="256 KiB"):
        manager.install("too-large.py", b"#" * (256 * 1024 + 1))


def test_admin_can_upload_load_and_uninstall_a_single_file_card(tmp_path):
    from moviesync.app import create_app

    app = create_app({"MOVIESYNC_DATA_DIR": str(tmp_path)}, start_scheduler=False)
    services = app.extensions["moviesync"]
    client = app.test_client()
    client.post("/api/setup", json={"username": "admin", "password": "password123"})
    with client.session_transaction() as session:
        csrf = session["csrf_token"]
    headers = {"X-CSRF-Token": csrf}

    response = client.post(
        "/api/cards/plugins",
        data={"file": (io.BytesIO(_plugin_source()), "upload-demo.py")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.get_json()["card_id"] == "upload-demo"
    assert services["card_registry"].get("upload-demo") is not None

    listing = client.get("/api/cards").get_json()
    assert listing["dynamic_install_enabled"] is True
    assert any(item["filename"] == "upload-demo.py" and item["loaded"] for item in listing["file_plugins"])

    response = client.delete("/api/cards/plugins/upload-demo.py", headers=headers)
    assert response.status_code == 200
    assert services["card_registry"].get("upload-demo") is None
    assert not (tmp_path / "cards" / "upload-demo.py").exists()


def test_pansou_is_seeded_as_a_removable_file_card(tmp_path):
    from moviesync.app import create_app

    app = create_app({"MOVIESYNC_DATA_DIR": str(tmp_path)}, start_scheduler=False)
    services = app.extensions["moviesync"]
    plugin_path = tmp_path / "cards" / "pansou.py"

    assert plugin_path.is_file()
    assert services["card_registry"].get("pansou") is not None

    services["file_card_plugins"].uninstall("pansou.py")
    assert services["card_registry"].get("pansou") is None

    restarted = create_app({"MOVIESYNC_DATA_DIR": str(tmp_path)}, start_scheduler=False)
    assert restarted.extensions["moviesync"]["card_registry"].get("pansou") is None


def test_builtin_cards_are_independent_single_file_plugins(tmp_path):
    from moviesync.app import create_app

    app = create_app({"MOVIESYNC_DATA_DIR": str(tmp_path)}, start_scheduler=False)
    services = app.extensions["moviesync"]
    registry = services["card_registry"]
    plugin_manager = services["file_card_plugins"]

    assert registry.get("telegram") is not None
    assert registry.get("pansou") is not None
    assert registry.get("quark") is not None
    assert registry.get("douban") is not None
    assert all((tmp_path / "cards" / name).is_file() for name in (
        "telegram.py", "pansou.py", "quark.py", "douban.py"
    ))

    removed = plugin_manager.uninstall("telegram.py")

    assert removed["card_id"] == "telegram"
    assert registry.get("telegram") is None
    assert registry.get("pansou") is not None
    assert registry.get("quark") is not None
    assert registry.get("douban") is not None


def test_uninstall_keeps_card_registered_by_another_owner(tmp_path):
    from moviesync.cards import Card, CardManifest

    plugin_dir = tmp_path / "cards"
    plugin_dir.mkdir()
    (plugin_dir / "sample-plugin.py").write_bytes(_plugin_source("sample-plugin"))
    registry = CardRegistry()
    manager = CardFilePluginManager(plugin_dir, registry, logging.getLogger("test"))
    manager.load_all()
    registry.unregister("sample-plugin")

    class OtherCard(Card):
        manifest = CardManifest(id="sample-plugin", name="Other", type="custom")

    other = OtherCard()
    registry.register(other)
    assert manager.list_plugins()[0]["loaded"] is False
    manager.uninstall("sample-plugin.py")
    assert registry.get("sample-plugin") is other


@pytest.mark.parametrize(
    ("reference_field", "card_id"),
    [("source_id", "telegram"), ("storage_target_id", "quark")],
)
def test_uninstall_rejects_cards_referenced_by_subscriptions(
    tmp_path, reference_field, card_id
):
    from moviesync.app import create_app

    app = create_app({"MOVIESYNC_DATA_DIR": str(tmp_path)}, start_scheduler=False)
    services = app.extensions["moviesync"]
    if reference_field == "storage_target_id":
        # Exercise the subscription-reference guard rather than the separate
        # safeguard for the currently selected default storage target.
        services["config"].set_default_storage_target_id("")
    services["subscriptions"].add_subscription(
        title="Referenced show",
        pwd_id="share123",
        source_id=card_id if reference_field == "source_id" else "",
        channel="movies" if reference_field == "source_id" else "",
        storage_target_id=card_id if reference_field == "storage_target_id" else "",
    )

    client = app.test_client()
    client.post("/api/setup", json={"username": "admin", "password": "password123"})
    with client.session_transaction() as session:
        csrf = session["csrf_token"]

    response = client.delete(
        f"/api/cards/plugins/{card_id}.py",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 409
    assert "自动追剧订阅" in response.get_json()["message"]
    assert (tmp_path / "cards" / f"{card_id}.py").is_file()
    assert services["card_registry"].get(card_id) is not None

def test_cards_api_uses_card_interface_for_configuration_status(tmp_path):
    """The platform should not special-case card IDs to determine configured state."""
    from moviesync.app import create_app
    from moviesync.cards import Card, CardManifest

    app = create_app({"MOVIESYNC_DATA_DIR": str(tmp_path)}, start_scheduler=False)
    services = app.extensions["moviesync"]

    class CustomConfiguredCard(Card):
        manifest = CardManifest(
            id="custom-configured",
            name="Custom Configured",
            type="custom",
            config_fields=({"key": "endpoint", "label": "Endpoint", "required": True},),
        )

    client = app.test_client()
    client.post("/api/setup", json={"username": "admin", "password": "password123"})
    services["card_registry"].register(CustomConfiguredCard())
    services["config"].save_card_config(
        "custom-configured", {"endpoint": "https://example.invalid"}
    )

    response = client.get("/api/cards")
    assert response.status_code == 200
    cards = response.get_json()["cards"]
    custom = next(item for item in cards if item["id"] == "custom-configured")
    assert custom["configured"] is True
    assert custom["health"]["status"] == "idle"


def test_cards_api_does_not_treat_quark_default_fid_as_configuration(tmp_path):
    from moviesync.app import create_app

    app = create_app({"MOVIESYNC_DATA_DIR": str(tmp_path)}, start_scheduler=False)
    client = app.test_client()
    client.post("/api/setup", json={"username": "admin", "password": "password123"})
    cards = client.get("/api/cards").get_json()["cards"]
    quark = next(item for item in cards if item["id"] == "quark")
    assert quark["configured"] is False
    assert quark["health"]["status"] == "idle"


def test_cards_api_does_not_treat_telegram_regex_defaults_as_configuration(tmp_path):
    from moviesync.app import create_app

    app = create_app({"MOVIESYNC_DATA_DIR": str(tmp_path)}, start_scheduler=False)
    client = app.test_client()
    client.post("/api/setup", json={"username": "admin", "password": "password123"})
    cards = client.get("/api/cards").get_json()["cards"]
    telegram = next(item for item in cards if item["id"] == "telegram")
    assert telegram["configured"] is False
    assert telegram["health"]["status"] == "unknown"



def test_legacy_persistent_douban_card_factory_is_migrated_safely(tmp_path):
    plugin_dir = tmp_path / "cards"
    plugin_dir.mkdir()
    marker_dir = plugin_dir / ".seeded"
    marker_dir.mkdir()
    (marker_dir / "douban.py.seeded").touch()
    plugin_path = plugin_dir / "douban.py"
    plugin_path.write_text(
        'from moviesync.clients.douban import DoubanClient\n'
        'from card_templates.douban import DoubanMetadataCard\n'
        '\n'
        '# Keep this local note when migrating the built-in factory.\n'
        'def create_card(context):\n'
        '    return DoubanMetadataCard(context["douban"])\n',
        encoding="utf-8",
    )

    manager = CardFilePluginManager(
        plugin_dir,
        CardRegistry(),
        logging.getLogger("test-card-plugins"),
        Path(__file__).resolve().parents[1] / "card_templates",
    )

    loaded = manager.load_all()

    assert "douban" in loaded
    assert manager.registry.get("douban") is not None
    migrated = plugin_path.read_text(encoding="utf-8")
    assert "return DoubanMetadataCard(DoubanClient())" in migrated
    assert "context[\"douban\"]" not in migrated
    assert "# Keep this local note" in migrated
