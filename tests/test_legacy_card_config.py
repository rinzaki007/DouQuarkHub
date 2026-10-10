"""Regression tests for legacy card migration boundaries."""

import json

from moviesync.config_store import ConfigStore
from moviesync.settings import DEFAULT_CATEGORY_FIDS


def test_valid_legacy_quark_and_telegram_config_migrate(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "quark_cookie": "legacy-cookie",
                "default_fid": "12345",
                "category_fids": {"电影": "67890"},
                "channels": [{"name": "旧频道", "id": "@legacy_channel"}],
                "resource_sources": [
                    {
                        "id": "telegram",
                        "enabled": False,
                        "health": {"status": "healthy", "message": "旧状态"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    store = ConfigStore(config_file, tmp_path / "legacy")
    migrated = store.load()

    assert migrated["cards"]["quark"]["config"]["cookie"] == "legacy-cookie"
    assert migrated["cards"]["quark"]["config"]["default_fid"] == "12345"
    assert migrated["cards"]["quark"]["config"]["category_fids"]["电影"] == "67890"
    assert migrated["cards"]["telegram"]["enabled"] is False
    assert migrated["cards"]["telegram"]["config"]["channels"] == [
        {"id": "legacy_channel", "name": "旧频道"}
    ]
    assert migrated["cards"]["telegram"]["config"]["health"]["status"] == "healthy"
    assert "quark_cookie" not in migrated
    assert "channels" not in migrated
    assert "resource_sources" not in migrated


def test_malformed_legacy_card_data_does_not_block_other_cards(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "cards": {
                    "quark": {
                        "enabled": True,
                        "config": {
                            "cookie": "keep-quark-cookie",
                            "default_fid": "../invalid/fid",
                            "category_fids": "not-an-object",
                        },
                    },
                    "telegram": {
                        "enabled": False,
                        "config": {
                            "channels": [{"name": "坏频道", "id": "https://invalid.example"}],
                            "health": ["malformed-health"],
                            "magic_regex": {"pattern": ".*", "replace": ""},
                        },
                    },
                    "third-party.storage": {
                        "enabled": True,
                        "config": {"endpoint": "https://storage.example", "marker": "preserve"},
                    },
                },
                "resource_sources": [
                    {"id": "telegram", "enabled": False, "health": ["invalid-source-health"]}
                ],
            }
        ),
        encoding="utf-8",
    )

    store = ConfigStore(config_file, tmp_path / "legacy")
    migrated = store.load()

    # A broken legacy Quark field is replaced with a safe value without losing
    # the card's valid credentials or unrelated card configuration.
    quark = migrated["cards"]["quark"]["config"]
    assert quark["cookie"] == "keep-quark-cookie"
    assert quark["default_fid"] == "0"
    assert quark["category_fids"] == {key: "" for key in DEFAULT_CATEGORY_FIDS}

    # Invalid Telegram channels/health are isolated to Telegram's own defaults.
    telegram = migrated["cards"]["telegram"]
    assert telegram["enabled"] is False
    assert telegram["config"]["channels"] == []
    assert telegram["config"]["health"]["status"] == "unknown"
    assert telegram["config"]["magic_regex"]["pattern"] == ".*"

    # A third-party card survives the legacy migration untouched.
    assert migrated["cards"]["third-party.storage"] == {
        "enabled": True,
        "config": {"endpoint": "https://storage.example", "marker": "preserve"},
    }
