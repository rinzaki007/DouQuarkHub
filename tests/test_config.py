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
    assert public["has_quark_cookie"] is True


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
