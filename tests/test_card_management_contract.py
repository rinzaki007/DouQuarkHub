from moviesync.cards import CardRegistry
from moviesync.cards_metadata import DoubanMetadataCard
from moviesync.services.resource_sources import TelegramResourceSource


def test_card_management_uses_registry_manifests():
    registry = CardRegistry()
    registry.register(DoubanMetadataCard(object()))
    registry.register(TelegramResourceSource(object()))

    cards = registry.manifests()

    assert {item["id"] for item in cards} == {"douban", "telegram"}
    assert {item["type"] for item in cards} == {"metadata_provider", "resource_source"}
