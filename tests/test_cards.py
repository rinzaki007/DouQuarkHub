"""通用卡片接口与注册表回归测试。"""

import pytest

from moviesync.cards import Card, CardManifest, CardRegistry
from card_templates.douban import DoubanMetadataCard
from card_templates.quark import QuarkStorageCard
from card_templates.telegram import TelegramResourceSource


class DemoCard(Card):
    manifest = CardManifest(
        id="demo.card",
        name="Demo",
        version="1.2.0",
        type="custom",
        capabilities=("demo.run", "demo.check"),
    )


def test_card_manifest_is_serializable():
    manifest = DemoCard.manifest.to_dict()

    assert manifest["id"] == "demo.card"
    assert manifest["version"] == "1.2.0"
    assert manifest["type"] == "custom"
    assert manifest["capabilities"] == ["demo.run", "demo.check"]


def test_card_registry_register_get_and_list():
    registry = CardRegistry()
    card = DemoCard()

    registry.register(card)

    assert registry.get("demo.card") is card
    assert registry.list() == [card]
    assert registry.manifests()[0]["name"] == "Demo"


def test_card_registry_can_find_by_type_and_capability():
    registry = CardRegistry()
    registry.register(DemoCard())

    assert registry.find_by_type("custom")[0].card_id == "demo.card"
    assert registry.find_by_capability("demo.run")[0].card_id == "demo.card"


def test_card_registry_rejects_duplicate_without_replace():
    registry = CardRegistry()
    registry.register(DemoCard())

    with pytest.raises(ValueError):
        registry.register(DemoCard())


def test_card_manifest_rejects_invalid_id():
    with pytest.raises(ValueError):
        CardManifest(id="Bad ID", name="Bad")



def test_telegram_resource_source_uses_card_interface():
    from card_templates.telegram import TelegramResourceSource

    class FakeTelegramClient:
        pass

    card = TelegramResourceSource(FakeTelegramClient())

    assert isinstance(card, Card)
    assert card.card_id == "telegram"
    assert card.card_type == "resource_source"
    assert "resource.search" in card.capabilities
    assert card.manifest.to_dict()["name"] == "Telegram"



def test_quark_storage_card_uses_storage_target_interface():
    from card_templates.quark import QuarkStorageCard
    from moviesync.cards import StorageTargetCard

    class FakeConfigStore:
        def get_cookie(self):
            return ""

    card = QuarkStorageCard(FakeConfigStore())

    assert isinstance(card, StorageTargetCard)
    assert card.card_id == "quark"
    assert card.card_type == "storage_target"
    assert "storage.transfer" in card.capabilities
    assert card.check()["status"] == "unconfigured"


def test_registry_contains_unified_card_manifest_contract():
    from card_templates.douban import DoubanMetadataCard
    from moviesync.services.resource_sources import TelegramResourceSource

    assert DoubanMetadataCard.manifest.type == "metadata_provider"
    assert TelegramResourceSource.manifest.type == "resource_source"
    assert "metadata.search" in DoubanMetadataCard.manifest.capabilities
    assert "resource.search" in TelegramResourceSource.manifest.capabilities



@pytest.mark.parametrize(
    "field, message",
    [
        ({"key": "value", "min_length": -1}, "min_length"),
        ({"key": "value", "min_length": 5, "max_length": 2}, "最小长度"),
        ({"key": "value", "pattern": "["}, "正则规则无效"),
        ({"key": "value", "format": "date"}, "格式规则无效"),
        ({"key": "value", "type": "boolean", "pattern": "yes"}, "pattern"),
    ],
)
def test_card_manifest_rejects_invalid_text_constraints(field, message):
    with pytest.raises(ValueError, match=message):
        CardManifest(
            id="invalid-schema",
            name="Invalid Schema",
            config_fields=(field,),
        )


def test_card_manifest_rejects_unsafe_or_oversized_regex_patterns():
    with pytest.raises(ValueError, match="嵌套重复"):
        CardManifest(
            id="unsafe-regex-card",
            name="Unsafe Regex",
            config_fields=(
                {"key": "value", "type": "string", "pattern": "(a+)+$"},
            ),
        )

    with pytest.raises(ValueError, match="不能超过 500"):
        CardManifest(
            id="long-regex-card",
            name="Long Regex",
            config_fields=(
                {"key": "value", "type": "string", "pattern": "a" * 501},
            ),
        )


def test_card_config_regex_input_is_bounded_without_manifest_max_length():
    from moviesync.cards import ResourceSourceCard
    from moviesync.config_store import ConfigValidationError

    class PatternCard(ResourceSourceCard):
        manifest = CardManifest(
            id="pattern-input-card",
            name="Pattern Input",
            type="resource_source",
            config_fields=(
                {"key": "value", "type": "string", "pattern": "^[a-z]+$"},
            ),
        )

        def search(self, movie, config):
            return []

        def check(self, config):
            return {"status": "healthy"}

    with pytest.raises(ConfigValidationError, match="不能超过 4096"):
        PatternCard().validate_config({"value": "a" * 4097})



def test_card_registry_closes_replaced_card():
    closed = []

    class ClosableCard(DemoCard):
        def __init__(self, name):
            self.name = name

        def close(self):
            closed.append(self.name)

    registry = CardRegistry()
    old = ClosableCard("old")
    new = ClosableCard("new")
    registry.register(old)
    registry.register(new, replace=True)

    assert registry.get("demo.card") is new
    assert closed == ["old"]


def test_card_registry_unregister_closes_card_and_returns_instance():
    closed = []

    class ClosableCard(DemoCard):
        def close(self):
            closed.append(self.card_id)

    registry = CardRegistry()
    card = ClosableCard()
    registry.register(card)

    assert registry.unregister("demo.card") is card
    assert registry.get("demo.card") is None
    assert closed == ["demo.card"]


def test_card_registry_close_all_isolates_cleanup_errors():
    closed = []

    class ClosableCard(DemoCard):
        def __init__(self, card_id, should_fail=False):
            self.manifest = CardManifest(id=card_id, name=card_id)
            self.should_fail = should_fail

        def close(self):
            closed.append(self.card_id)
            if self.should_fail:
                raise RuntimeError("cleanup failed")

    registry = CardRegistry()
    registry.register(ClosableCard("first.card", should_fail=True))
    registry.register(ClosableCard("second.card"))

    registry.close_all()

    assert registry.list() == []
    assert closed == ["first.card", "second.card"]


def test_card_registry_does_not_close_same_instance_when_re_registered():
    closed = []

    class ClosableCard(DemoCard):
        def close(self):
            closed.append(self.card_id)

    registry = CardRegistry()
    card = ClosableCard()
    registry.register(card)
    registry.register(card, replace=True)

    assert closed == []



def test_card_registry_migrates_old_config_and_persists_version():
    from copy import deepcopy

    class FakeConfigStore:
        def __init__(self):
            self.data = {
                "cards": {
                    "versioned.card": {
                        "enabled": False,
                        "config": {"old_name": "value", "obsolete": True},
                    }
                }
            }

        def load(self):
            return deepcopy(self.data)

        def save_card_config(
            self,
            card_id,
            incoming,
            *,
            enabled=None,
            config_version=None,
            replace_config=False,
        ):
            saved = self.data["cards"][card_id]
            saved["config"] = deepcopy(incoming) if replace_config else {
                **saved.get("config", {}),
                **deepcopy(incoming),
            }
            if enabled is not None:
                saved["enabled"] = enabled
            if config_version is not None:
                saved["config_version"] = config_version
            return deepcopy(saved)

    class VersionedCard(DemoCard):
        manifest = CardManifest(
            id="versioned.card",
            name="Versioned",
            config_version=2,
        )

        def migrate_config(self, config, from_version):
            assert from_version == 1
            return {"new_name": config["old_name"]}

    registry = CardRegistry()
    registry.register(VersionedCard())
    store = FakeConfigStore()

    assert registry.migrate_configs(store) == ["versioned.card"]
    saved = store.data["cards"]["versioned.card"]
    assert saved["config"] == {"new_name": "value"}
    assert saved["config_version"] == 2
    assert saved["enabled"] is False


def test_card_registry_keeps_old_config_when_migration_fails():
    from copy import deepcopy

    class FakeConfigStore:
        def __init__(self):
            self.data = {
                "cards": {
                    "broken.migration": {
                        "enabled": True,
                        "config": {"keep": "me"},
                    }
                }
            }

        def load(self):
            return deepcopy(self.data)

        def save_card_config(self, *args, **kwargs):
            raise AssertionError("failed migration must not save")

    class BrokenMigrationCard(DemoCard):
        manifest = CardManifest(
            id="broken.migration",
            name="Broken Migration",
            config_version=3,
        )

        def migrate_config(self, config, from_version):
            raise RuntimeError("migration failed")

    registry = CardRegistry()
    registry.register(BrokenMigrationCard())
    store = FakeConfigStore()

    assert registry.migrate_configs(store) == []
    assert store.data["cards"]["broken.migration"]["config"] == {"keep": "me"}
    assert "config_version" not in store.data["cards"]["broken.migration"]


def test_card_registry_does_not_downgrade_newer_saved_config():
    from copy import deepcopy

    class FakeConfigStore:
        def __init__(self):
            self.data = {
                "cards": {
                    "future.card": {
                        "enabled": True,
                        "config_version": 4,
                        "config": {"future": True},
                    }
                }
            }

        def load(self):
            return deepcopy(self.data)

        def save_card_config(self, *args, **kwargs):
            raise AssertionError("future config version must not be overwritten")

    class OlderCard(DemoCard):
        manifest = CardManifest(
            id="future.card",
            name="Older Card",
            config_version=2,
        )

        def migrate_config(self, config, from_version):
            raise AssertionError("must not migrate a newer saved version")

    registry = CardRegistry()
    registry.register(OlderCard())
    store = FakeConfigStore()

    assert registry.migrate_configs(store) == []
    assert store.data["cards"]["future.card"]["config_version"] == 4


def test_card_manifest_requires_positive_config_version():
    with pytest.raises(ValueError, match="config_version"):
        CardManifest(id="bad-version", name="Bad Version", config_version=0)
