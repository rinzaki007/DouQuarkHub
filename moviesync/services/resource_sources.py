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


class ResourceSource:
    """资源发现源的统一接口。"""

    source_id = "unknown"
    name = "未命名资源源"
    source_type = "custom"

    def search(self, movie: object, config: dict) -> list[dict[str, Any]]:
        raise NotImplementedError

    def check(self, config: dict) -> dict[str, Any]:
        raise NotImplementedError


class TelegramResourceSource(ResourceSource):
    source_id = "telegram"
    name = "Telegram"
    source_type = "telegram"

    def __init__(self, client: TelegramClient):
        self.client = client

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

    def __init__(self, telegram: TelegramClient, config_store, logger):
        self.logger = logger
        self.config_store = config_store
        self.sources: dict[str, ResourceSource] = {
            "telegram": TelegramResourceSource(telegram),
        }
        self.lock = RLock()

    def _enabled_sources(self, config: dict) -> list[ResourceSource]:
        definitions = {
            str(item.get("id")): item
            for item in config.get("resource_sources", [])
            if isinstance(item, dict)
        }
        enabled = []
        for source_id, source in self.sources.items():
            item = definitions.get(source_id, {})
            if item.get("enabled", True):
                enabled.append(source)
        return enabled

    def search(self, movie: object, config: dict) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for source in self._enabled_sources(config):
            try:
                results.extend(source.search(movie, config))
            except Exception as exc:
                self.logger.exception(
                    "资源源 %s 搜索异常: %s",
                    source.source_id,
                    exc,
                )
        return results

    def check_all(self) -> list[dict[str, Any]]:
        config = self.config_store.load()
        definitions = {
            str(item.get("id")): item
            for item in config.get("resource_sources", [])
            if isinstance(item, dict)
        }
        results = []

        for source_id, source in self.sources.items():
            definition = definitions.get(source_id, {})
            if not definition.get("enabled", True):
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
                    check = source.check(config)
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
        config = self.config_store.load()
        definitions = config.get("resource_sources") or []
        return [dict(item) for item in definitions if isinstance(item, dict)]
