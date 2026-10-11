"""Unified playback-provider discovery and dispatch."""
from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any

from ..cards import Card, CardRegistry, PlaybackProviderCard


class PlaybackProviderManager:
    def __init__(self, registry: CardRegistry, config_store, logger):
        self.registry = registry
        self.config_store = config_store
        self.logger = logger

    def load_plugins(self, context: dict[str, Any] | None = None) -> list[str]:
        loaded = []
        try:
            candidates = entry_points(group="moviesync.playback_providers")
        except Exception:
            self.logger.exception("读取在线播放卡片插件入口失败")
            return loaded
        for entry_point in candidates:
            card = None
            try:
                factory = entry_point.load()
                if not callable(factory):
                    raise TypeError("播放卡片插件入口必须是工厂函数")
                card = factory(dict(context or {}))
                if not isinstance(card, PlaybackProviderCard):
                    raise TypeError("播放卡片插件工厂必须返回 PlaybackProviderCard 实例")
                self.registry.register(card)
                loaded.append(card.card_id)
                self.logger.info("已加载在线播放卡片插件：%s", card.card_id)
            except Exception:
                if isinstance(card, Card):
                    try:
                        if self.registry.get(card.card_id) is not card:
                            card.close()
                    except Exception:
                        self.logger.exception("清理未注册播放卡片失败")
                self.logger.exception("在线播放卡片插件 %s 加载失败", entry_point.name)
        return loaded

    def _active(self, card: PlaybackProviderCard) -> bool:
        try:
            config = self.config_store.load()
        except Exception:
            self.logger.exception("读取在线播放卡片配置失败")
            return False
        cards = config.get("cards", {}) if isinstance(config, dict) else {}
        saved = cards.get(card.card_id, {}) if isinstance(cards, dict) else {}
        return not isinstance(saved, dict) or bool(saved.get("enabled", True))

    def list_providers(self) -> list[dict[str, Any]]:
        providers = []
        for card in self.registry.find_by_type("playback_provider"):
            if not isinstance(card, PlaybackProviderCard) or not self._active(card):
                continue
            try:
                configured = bool(card.is_configured({}))
            except Exception:
                self.logger.exception("读取播放卡片 %s 配置状态失败", card.card_id)
                configured = False
            providers.append({
                "id": card.card_id,
                "name": card.manifest.name,
                "description": card.manifest.description,
                "configured": configured,
            })
        return providers

    def get(self, provider_id: str) -> PlaybackProviderCard | None:
        card = self.registry.get(str(provider_id or "").strip())
        if not isinstance(card, PlaybackProviderCard) or not self._active(card):
            return None
        return card

    def list_files(self, provider_id: str, parent_fid: str = "0") -> list[dict[str, Any]]:
        card = self.get(provider_id)
        if card is None:
            raise LookupError("在线播放卡片尚未加载或已停用")
        if not card.is_configured({}):
            raise RuntimeError("请先在夸克存储卡片中配置有效 Cookie")
        return card.list_files(parent_fid)

    def resolve_playback(self, provider_id: str, fid: str) -> dict[str, Any]:
        card = self.get(provider_id)
        if card is None:
            raise LookupError("在线播放卡片尚未加载或已停用")
        if not card.is_configured({}):
            raise RuntimeError("请先在夸克存储卡片中配置有效 Cookie")
        return card.resolve_playback(fid)
