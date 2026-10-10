"""统一影视元数据提供方管理。

元数据提供方是独立卡片。单张卡片异常或返回值不符合接口约定时，
不应让首页、搜索或其它提供方一起失败。
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from ..cards import CardRegistry, MetadataProviderCard

T = TypeVar("T")


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

    def _providers(
        self,
        provider_id: str | None = None,
        capability: str | None = None,
    ) -> list[MetadataProviderCard]:
        if provider_id:
            card = self.registry.get(provider_id)
            candidates = [card] if isinstance(card, MetadataProviderCard) else []
        else:
            candidates = [
                card
                for card in self.registry.find_by_type("metadata_provider")
                if isinstance(card, MetadataProviderCard)
            ]

        result = []
        for card in candidates:
            if not self._is_enabled(card):
                continue
            if capability and capability not in card.capabilities:
                continue
            result.append(card)
        return result

    def _call(
        self,
        operation: str,
        capability: str,
        callback: Callable[[MetadataProviderCard], T],
        *,
        provider_id: str | None = None,
        empty: T,
        valid: Callable[[object], bool],
    ) -> T:
        """Call providers independently, falling through on failures/empty results.

        An explicitly selected provider is never silently replaced by another
        provider, so the caller's choice remains authoritative.
        """
        providers = self._providers(provider_id, capability)
        if not providers:
            return empty

        for card in providers:
            try:
                result = callback(card)
                if not valid(result):
                    raise TypeError(f"{operation} 返回值不符合卡片接口约定")
                if result:
                    return result
            except Exception:
                self.logger.exception(
                    "元数据卡片 %s 的 %s 调用失败",
                    card.card_id,
                    operation,
                )
                if provider_id:
                    return empty

        return empty

    @staticmethod
    def _valid_items(value: object) -> bool:
        return isinstance(value, list) and all(isinstance(item, dict) for item in value)

    def list_movies(
        self,
        tag: str = "电影",
        sort_type: str = "U",
        provider_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._call(
            "list_movies",
            "metadata.list",
            lambda card: card.list_movies(tag, sort_type),
            provider_id=provider_id,
            empty=[],
            valid=self._valid_items,
        )

    def search(self, query: str, provider_id: str | None = None) -> list[dict[str, Any]]:
        return self._call(
            "search",
            "metadata.search",
            lambda card: card.search(query),
            provider_id=provider_id,
            empty=[],
            valid=self._valid_items,
        )

    def get_detail(self, item_id: str, provider_id: str | None = None) -> dict[str, Any] | None:
        return self._call(
            "get_detail",
            "metadata.detail",
            lambda card: card.get_detail(item_id),
            provider_id=provider_id,
            empty=None,
            valid=lambda value: value is None or isinstance(value, dict),
        )
