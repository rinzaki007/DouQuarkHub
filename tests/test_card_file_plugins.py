"""Regression tests for trusted, persistent single-file card plugins."""
from __future__ import annotations

import io
import logging

import pytest

from moviesync.cards import Card, CardManifest, CardRegistry
from moviesync.card_plugins import CardFilePluginManager


def _plugin_source(card_id: str = "upload-demo") -> bytes:
    return f'''from moviesync.cards import Card, CardManifest


class DemoCard(Card):
    manifest = CardManifest(id="{card_id}", name="Uploaded Demo", type="custom")


def create_card(context):
    return DemoCard()
'''.encode("utf-8")


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
