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
