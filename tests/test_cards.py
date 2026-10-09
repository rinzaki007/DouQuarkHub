"""通用卡片接口与注册表回归测试。"""

import pytest

from moviesync.cards import Card, CardManifest, CardRegistry


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
    from moviesync.services.resource_sources import TelegramResourceSource

    class FakeTelegramClient:
        pass

    card = TelegramResourceSource(FakeTelegramClient())

    assert isinstance(card, Card)
    assert card.card_id == "telegram"
    assert card.card_type == "resource_source"
    assert "resource.search" in card.capabilities
    assert card.manifest.to_dict()["name"] == "Telegram"



def test_quark_storage_card_uses_storage_target_interface():
    from moviesync.cards import QuarkStorageCard, StorageTargetCard

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
    from moviesync.cards_metadata import DoubanMetadataCard
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
