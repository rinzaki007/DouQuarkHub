"""资源来源抽象层。

用途：将资源发现入口与 MovieSync 核心业务解耦。当前内置 Telegram，
以后可在不改搜索、任务中心和转存逻辑的情况下增加其他合法资源源。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import RLock
from typing import Any

from ..cards import CardManifest, CardRegistry, ResourceSourceCard
from ..clients.telegram import TelegramClient


class ResourceSource(ResourceSourceCard):
    """资源发现卡片的兼容基类。

    旧代码仍可继续通过 ResourceSource 使用，新的实现统一遵循 Card 接口。
    """

    source_id = "unknown"
    name = "未命名资源源"
    source_type = "custom"
    manifest = CardManifest(
        id="unknown.resource",
        name="未命名资源源",
        type="resource_source",
        capabilities=("resource.search", "resource.health_check"),
    )

    def search(self, movie: object, config: dict) -> list[dict[str, Any]]:
        raise NotImplementedError

    def check(self, config: dict) -> dict[str, Any]:
        raise NotImplementedError


class TelegramResourceSource(ResourceSource):
    source_id = "telegram"
    name = "Telegram"
    source_type = "telegram"
    manifest = CardManifest(
        id="telegram",
        name="Telegram",
        version="1.0.0",
        type="resource_source",
        description="Telegram 公开频道资源发现卡片",
        capabilities=("resource.search", "resource.health_check"),
    )

    def __init__(self, client: TelegramClient, config_store=None):
        self.client = client
        self.config_store = config_store

    def search(self, movie: object, config: dict) -> list[dict[str, Any]]:
        channels = config.get("channels") or []
        title = str(
            movie.get("title", movie.get("name", ""))
            if isinstance(movie, dict)
            else movie
        ).strip()
        if not title or not channels:
            return []

        results: list[dict[str, Any]] = []
        with ThreadPoolExecutor(
            max_workers=min(8, max(1, len(channels)))
        ) as executor:
            futures = [
                executor.submit(self.client.search_channel, channel, title)
                for channel in channels
            ]
            for future in futures:
                try:
                    for item in future.result():
                        results.append(
                            {
                                **item,
                                "source_id": self.source_id,
                                "source_name": self.name,
                                "storage_target_id": item.get("storage_target_id", ""),
                            }
                        )
                except Exception:
                    continue
        return results

    def check(self, config: dict) -> dict[str, Any]:
        channels = config.get("channels") or []
        if not channels:
            return {
                "status": "idle",
                "message": "未配置 Telegram 频道",
                "total": 0,
                "valid_count": 0,
            }

        with ThreadPoolExecutor(
            max_workers=min(8, max(1, len(channels)))
        ) as executor:
            results = list(
                executor.map(
                    self.client.check_channel_detail,
                    channels,
                )
            )

        channel_results = []
        for channel, detail in zip(channels, results, strict=True):
            channel_id = str(
                channel.get("id", "")
                if isinstance(channel, dict)
                else channel
            ).strip().lstrip("@")
            channel_name = str(
                channel.get("name", channel_id)
                if isinstance(channel, dict)
                else channel_id
            ).strip() or channel_id
            channel_results.append(
                {
                    "id": channel_id,
                    "name": channel_name,
                    **detail,
                }
            )

        valid_count = sum(
            item.get("status") == "healthy"
            for item in channel_results
        )
        total = len(channels)
        if valid_count == total:
            status = "healthy"
            message = "所有已配置频道正常"
        elif valid_count:
            status = "degraded"
            message = f"{total - valid_count} 个频道不可用"
        else:
            status = "unavailable"
            message = "所有已配置频道均不可用"

        return {
            "status": status,
            "message": message,
            "total": total,
            "valid_count": valid_count,
            "channels": channel_results,
        }


class ResourceSourceManager:
    """管理已注册资源源，并提供统一搜索/健康检查入口。"""

    def __init__(
        self,
        telegram: TelegramClient,
        config_store,
        logger,
        registry: CardRegistry | None = None,
    ):
        self.logger = logger
        self.config_store = config_store
        self.registry = registry or CardRegistry()
        self.registry.register(TelegramResourceSource(telegram))
        # 保留 sources 属性，兼容现有调用方；新代码优先通过 registry 发现卡片。
        self.sources: dict[str, ResourceSource] = {
            card.card_id: card
            for card in self.registry.list()
            if isinstance(card, ResourceSource)
        }
        self.lock = RLock()

    def get_cards(self) -> list[dict[str, Any]]:
        """返回已加载资源卡片的 Manifest。"""
        return self.registry.manifests()

    def _card_config(self, config: dict, source_id: str) -> dict[str, Any]:
        cards = config.get("cards") if isinstance(config, dict) else {}
        card = cards.get(source_id) if isinstance(cards, dict) else {}
        if not isinstance(card, dict):
            return {}
        card_config = card.get("config")
        return dict(card_config) if isinstance(card_config, dict) else {}

    def _enabled_sources(self, config: dict) -> list[ResourceSource]:
        enabled = []
        cards = config.get("cards") if isinstance(config, dict) else {}
        for source_id, source in self.sources.items():
            card = cards.get(source_id) if isinstance(cards, dict) else {}
            if not isinstance(card, dict) or card.get("enabled", True):
                enabled.append(source)
        return enabled

    def search(self, movie: object, config: dict) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for source in self._enabled_sources(config):
            try:
                results.extend(source.search(movie, self._card_config(config, source.source_id)))
            except Exception as exc:
                self.logger.exception(
                    "资源源 %s 搜索异常: %s",
                    source.source_id,
                    exc,
                )
        return results

    def check_all(self) -> list[dict[str, Any]]:
        config = self.config_store.load()
        cards = config.get("cards") if isinstance(config, dict) else {}
        results = []

        for source_id, source in self.sources.items():
            card = cards.get(source_id) if isinstance(cards, dict) else {}
            enabled = not isinstance(card, dict) or bool(card.get("enabled", True))
            if not enabled:
                result = {
                    "id": source_id,
                    "name": source.name,
                    "type": source.source_type,
                    "enabled": False,
                    "status": "disabled",
                    "message": "资源源已停用",
                    "total": 0,
                    "valid_count": 0,
                }
            else:
                try:
                    check = source.check(self._card_config(config, source_id))
                    result = {
                        "id": source_id,
                        "name": source.name,
                        "type": source.source_type,
                        "enabled": True,
                        **check,
                    }
                except Exception as exc:
                    self.logger.exception(
                        "资源源 %s 健康检查异常",
                        source_id,
                    )
                    result = {
                        "id": source_id,
                        "name": source.name,
                        "type": source.source_type,
                        "enabled": True,
                        "status": "unavailable",
                        "message": str(exc)[:200],
                        "total": 0,
                        "valid_count": 0,
                    }

            results.append(result)
            self.config_store.update_resource_source_health(
                source_id,
                result["status"],
                result.get("message", ""),
                result.get("channels"),
            )

        return results

    def get_status(self) -> list[dict[str, Any]]:
        return self.config_store.get_resource_sources()
