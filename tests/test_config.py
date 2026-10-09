"""配置层单元测试。

覆盖：敏感 Cookie 保留、公共配置脱敏、频道规范化/去重以及非法频道拒绝。
"""
from moviesync.config_store import ConfigStore, ConfigValidationError


def test_config_preserves_secret_when_not_replaced(tmp_path):
    store = ConfigStore(tmp_path / "config.json", tmp_path / "legacy")
    store.save({"quark_cookie": "secret-cookie", "channels": [{"name": "测试", "id": "test_channel"}]})
    store.save({"default_fid": "123"})
    assert store.get_cookie() == "secret-cookie"
    public = store.public()
    assert "quark_cookie" not in public
    assert public["cards"]["quark"]["config"]["has_cookie"] is True


def test_channels_are_normalized_and_deduplicated(tmp_path):
    store = ConfigStore(tmp_path / "config.json", tmp_path / "legacy")
    channels = store.save_channels([
        {"name": "A", "id": "@channel_a"},
        {"name": "B", "id": "channel_a"},
    ])
    assert channels == [{"id": "channel_a", "name": "A"}]


def test_invalid_channel_is_rejected(tmp_path):
    store = ConfigStore(tmp_path / "config.json", tmp_path / "legacy")
    try:
        store.save_channels([{"name": "bad", "id": "https://evil.example/a"}])
    except ConfigValidationError:
        pass
    else:
        raise AssertionError("invalid channel should be rejected")


def test_config_schema_version_is_present(tmp_path):
    from moviesync.config_store import CONFIG_SCHEMA_VERSION, ConfigStore

    store = ConfigStore(tmp_path / "config.json", tmp_path / "legacy")
    assert store.load()["schema_version"] == CONFIG_SCHEMA_VERSION


def test_resource_source_defaults_and_health_persist(tmp_path):
    store = ConfigStore(tmp_path / "config.json", tmp_path / "legacy")
    sources = store.get_resource_sources()
    assert sources[0]["id"] == "telegram"
    assert sources[0]["enabled"] is True

    store.update_resource_source_health("telegram", "healthy", "所有已配置频道正常")
    health = store.get_resource_sources()[0]["health"]
    assert health["status"] == "healthy"
    assert health["message"] == "所有已配置频道正常"
    assert health["last_checked_at"] is not None



def test_quark_settings_are_stored_inside_card_config(tmp_path):
    store = ConfigStore(tmp_path / "config.json", tmp_path / "legacy")
    store.save({
        "quark_cookie": "secret-cookie",
        "default_fid": "123",
        "category_fids": {"电影": "456"},
    })

    config = store.load()
    assert config["cards"]["quark"]["config"]["cookie"] == "secret-cookie"
    assert config["cards"]["quark"]["config"]["default_fid"] == "123"
    assert config["cards"]["quark"]["config"]["category_fids"]["电影"] == "456"
    assert "quark_cookie" not in config
    assert "default_fid" not in config
    assert "category_fids" not in config


def test_legacy_quark_config_is_migrated_on_load(tmp_path):
    import json

    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({
            "quark_cookie": "legacy-cookie",
            "default_fid": "789",
            "category_fids": {"电影": "101112"},
            "schema_version": 3,
        }),
        encoding="utf-8",
    )

    store = ConfigStore(config_file, tmp_path / "legacy")
    quark = store.get_quark_config()

    assert quark["cookie"] == "legacy-cookie"
    assert quark["default_fid"] == "789"
    assert quark["category_fids"]["电影"] == "101112"
    persisted = __import__("json").loads(config_file.read_text(encoding="utf-8"))
    assert persisted["schema_version"] >= 5
    assert "quark_cookie" not in persisted
    assert persisted["cards"]["quark"]["config"]["cookie"] == "legacy-cookie"


def test_telegram_settings_are_stored_inside_card_config(tmp_path):
    store = ConfigStore(tmp_path / "config.json", tmp_path / "legacy")
    saved = store.save_telegram_config({
        "channels": [{"name": "Telegram", "id": "@movie_channel"}],
    })
    assert saved["config"]["channels"] == [
        {"id": "movie_channel", "name": "Telegram"}
    ]
    config = store.load()
    assert config["cards"]["telegram"]["config"]["channels"] == [
        {"id": "movie_channel", "name": "Telegram"}
    ]
    assert "channels" not in config
    assert "resource_sources" not in config


def test_legacy_telegram_config_is_migrated_on_load(tmp_path):
    import json

    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({
            "channels": [{"name": "旧频道", "id": "@legacy_channel"}],
            "resource_sources": [{
                "id": "telegram",
                "enabled": False,
                "health": {"status": "healthy", "message": "旧状态"},
            }],
            "schema_version": 3,
        }),
        encoding="utf-8",
    )

    store = ConfigStore(config_file, tmp_path / "legacy")
    config = store.load()
    telegram = config["cards"]["telegram"]

    assert telegram["enabled"] is False
    assert telegram["config"]["channels"] == [
        {"id": "legacy_channel", "name": "旧频道"}
    ]
    assert telegram["config"]["health"]["status"] == "healthy"
    assert "channels" not in config
    assert "resource_sources" not in config


def test_default_storage_target_is_persisted(tmp_path):
    store = ConfigStore(tmp_path / "config.json", tmp_path / "legacy")
    assert store.get_default_storage_target_id() == ""
    assert store.set_default_storage_target_id("quark") == "quark"
    assert store.get_default_storage_target_id() == "quark"


def test_openlist_url_can_be_empty(tmp_path):
    store = ConfigStore(tmp_path / "config.json", tmp_path / "legacy")
    saved = store.save({"openlist_url": ""})
    assert saved["openlist_url"] == ""


def test_full_config_save_preserves_telegram_magic_regex(tmp_path):
    store = ConfigStore(tmp_path / "config.json", tmp_path / "legacy")
    channels = [{"id": "movie_channel", "name": "电影频道"}]
    magic_regex = {
        "pattern": r"(?i)\bS\d{2}E\d{2}\b",
        "replace": r"\g<0>",
    }

    store.save({
        "cards": {
            "telegram": {
                "enabled": True,
                "config": {
                    "channels": channels,
                    "magic_regex": magic_regex,
                },
            },
        },
    })

    config = store.get_telegram_config()
    assert config["channels"] == channels
    assert config["magic_regex"] == magic_regex
