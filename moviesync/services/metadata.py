"""统一影视元数据提供方管理。"""
from __future__ import annotations

from typing import Any

from ..cards import CardRegistry, MetadataProviderCard


class MetadataProviderManager:
    def __init__(self, registry: CardRegistry, logger, config_store=None):
        self.registry = registry
        self.logger = logger
        self.config_store = config_store

    def _is_enabled(self, card: MetadataProviderCard) -> bool:
        if self.config_store is None:
            return True
        config = self.config_store.load()
        cards = config.get("cards", {}) if isinstance(config, dict) else {}
        saved = cards.get(card.card_id, {}) if isinstance(cards, dict) else {}
        return not isinstance(saved, dict) or bool(saved.get("enabled", True))

    def _get(self, provider_id: str | None = None) -> MetadataProviderCard | None:
        if provider_id:
            card = self.registry.get(provider_id)
            return card if isinstance(card, MetadataProviderCard) and self._is_enabled(card) else None
        return next(
            (card for card in self.registry.find_by_type("metadata_provider") if self._is_enabled(card)),
            None,
        )

    def list_movies(
        self,
        tag: str = "电影",
        sort_type: str = "U",
        provider_id: str | None = None,
    ) -> list[dict[str, Any]]:
        card = self._get(provider_id)
        if not card:
            return []
        return card.list_movies(tag, sort_type)

    def search(self, query: str, provider_id: str | None = None) -> list[dict[str, Any]]:
        card = self._get(provider_id)
        if not card:
            return []
        return card.search(query)

    def get_detail(self, item_id: str, provider_id: str | None = None) -> dict[str, Any] | None:
        card = self._get(provider_id)
        if not card:
            return None
        return card.get_detail(item_id)
