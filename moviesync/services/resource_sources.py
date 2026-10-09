"""资源来源抽象层。

用途：将资源发现入口与 MovieSync 核心业务解耦。当前内置 Telegram，
以后可在不改搜索、任务中心和转存逻辑的情况下增加其他合法资源源。
"""

from __future__ import annotations

from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import entry_points
from threading import RLock
from typing import Any

from ..cards import CardManifest, CardRegistry, ResourceSourceCard
from ..clients.telegram import TelegramClient
from .filename_rules import parse_tv_episode


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

    def search_channel(self, channel: object, title: str, config: dict) -> list[dict[str, Any]]:
        # 自动追剧要扫描频道最近的消息，而不是只依赖 Telegram 的标题查询结果；
        # 后续仍由客户端做标题匹配并受页数上限保护。
        return self.client.search_channel(channel, title, scan_all=True)


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
        resource_cards: Iterable[ResourceSourceCard] | None = None,
    ):
        self.logger = logger
        self.config_store = config_store
        self.registry = registry or CardRegistry()
        self.sources: dict[str, ResourceSourceCard] = {}
        self.lock = RLock()

        # 默认资源源仅在未注册时加载；允许应用装配层预先注册卡片。
        if self.registry.get("telegram") is None:
            self.registry.register(TelegramResourceSource(telegram))
        for card in self.registry.find_by_type("resource_source"):
            if isinstance(card, ResourceSourceCard):
                self.sources[card.card_id] = card
        for card in resource_cards or ():
            self.register(card)

    def register(self, card: ResourceSourceCard, *, replace: bool = False) -> ResourceSourceCard:
        """注册资源来源卡片。第三方实现应由应用启动时的可信代码显式装配。"""
        if not isinstance(card, ResourceSourceCard):
            raise TypeError("资源来源卡片必须继承 ResourceSourceCard")
        if card.card_type != "resource_source":
            raise ValueError("卡片类型必须是 resource_source")
        registered = self.registry.register(card, replace=replace)
        self.sources[registered.card_id] = registered
        return registered

    @staticmethod
    def _source_name(source: ResourceSourceCard) -> str:
        return str(getattr(source, "name", "") or source.manifest.name or source.card_id)

    @staticmethod
    def _source_type(source: ResourceSourceCard) -> str:
        return str(getattr(source, "source_type", "") or source.card_type)


    def load_plugins(self, context: dict[str, Any] | None = None) -> list[str]:
        """加载已安装 Python 包声明的资源卡片插件。

        插件通过 moviesync.resource_sources entry point 暴露一个工厂函数，
        工厂接收 context 字典并返回 ResourceSourceCard。仅加载环境中已安装
        的可信 Python 包；不接受从 Web 上传或执行任意代码。
        """
        loaded: list[str] = []
        plugin_context = dict(context or {})
        try:
            candidates = entry_points(group="moviesync.resource_sources")
        except Exception as exc:
            self.logger.exception("读取资源卡片插件入口失败: %s", exc)
            return loaded

        for entry_point in candidates:
            try:
                factory = entry_point.load()
                if not callable(factory):
                    raise TypeError("插件入口必须指向可调用的工厂函数")
                card = factory(plugin_context)
                self.register(card)
                loaded.append(card.card_id)
                self.logger.info("已加载资源卡片插件: %s", card.card_id)
            except Exception as exc:
                self.logger.exception("资源卡片插件 %s 加载失败: %s", entry_point.name, exc)
        return loaded


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

    def _enabled_sources(self, config: dict) -> list[ResourceSourceCard]:
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
                items = source.search(movie, self._card_config(config, source.card_id))
                if not isinstance(items, list):
                    raise TypeError("资源卡片 search 必须返回列表")
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    results.append({
                        **item,
                        "source_id": str(item.get("source_id") or source.card_id),
                        "source_name": str(item.get("source_name") or self._source_name(source)),
                    })
            except Exception as exc:
                self.logger.exception(
                    "资源源 %s 搜索异常: %s",
                    source.card_id,
                    exc,
                )
        return results

    def parse_tv_episode(self, source_id: str, file_name: str) -> tuple[int | None, int | None]:
        """通过对应资源卡片的配置解析集数，核心订阅逻辑不绑定具体正则。"""
        config = self.config_store.load()
        source = self.sources.get(str(source_id))
        card_config = self._card_config(config, source.card_id) if source else {}
        return parse_tv_episode(file_name, card_config.get("magic_regex"))

    def search_channel(self, source_id: str, channel: object, title: str) -> list[dict[str, Any]]:
        config = self.config_store.load()
        source = self.sources.get(str(source_id))
        if not source:
            return []
        cards = config.get("cards") if isinstance(config, dict) else {}
        card = cards.get(source.card_id) if isinstance(cards, dict) else {}
        if isinstance(card, dict) and not card.get("enabled", True):
            return []
        try:
            return source.search_channel(
                channel,
                str(title or "").strip(),
                self._card_config(config, source.card_id),
            )
        except Exception as exc:
            self.logger.exception("资源源 %s 频道检索异常: %s", source.card_id, exc)
            return []


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
                    "name": self._source_name(source),
                    "type": self._source_type(source),
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
                        "name": self._source_name(source),
                        "type": self._source_type(source),
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
                        "name": self._source_name(source),
                        "type": self._source_type(source),
                        "enabled": True,
                        "status": "unavailable",
                        "message": str(exc)[:200],
                        "total": 0,
                        "valid_count": 0,
                    }

            results.append(result)
            update_health = getattr(self.config_store, "update_resource_source_health", None)
            if callable(update_health):
                update_health(
                    source_id,
                    result["status"],
                    result.get("message", ""),
                    result.get("channels"),
                )

        return results

    def get_status(self) -> list[dict[str, Any]]:
        return self.config_store.get_resource_sources()
