"""统一影视元数据提供方管理。"""
from __future__ import annotations

from typing import Any

from ..cards import CardRegistry, MetadataProviderCard


class MetadataProviderManager:
    def __init__(self, registry: CardRegistry, logger):
        self.registry = registry
        self.logger = logger

    def _get(self, provider_id: str | None = None) -> MetadataProviderCard | None:
        cards = self.registry.find_by_type("metadata_provider")
        if provider_id:
            card = self.registry.get(provider_id)
            return card if isinstance(card, MetadataProviderCard) else None
        return cards[0] if cards else None

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
