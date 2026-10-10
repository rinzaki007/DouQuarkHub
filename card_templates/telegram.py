"""Standalone Telegram resource-source card shipped as one Python file."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from moviesync.cards import CardManifest, ResourceSourceCard
from moviesync.clients.telegram import TelegramClient
from moviesync.errors import ConfigValidationError

_CHANNEL_ID_RE = re.compile(r"^[A-Za-z0-9_]{2,64}$")
_MAX_CHANNELS = 100


def _normalize_channels(channels: object) -> list[dict[str, str]]:
    """Normalize Telegram channel input locally; do not call ConfigStore internals."""
    if channels is None:
        return []
    if not isinstance(channels, list):
        raise ConfigValidationError("channels 必须是数组")

    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(channels):
        if isinstance(item, str):
            channel_id = item.strip().lstrip("@")
            name = channel_id
        elif isinstance(item, dict):
            channel_id = str(item.get("id", "")).strip().lstrip("@")
            name = str(item.get("name", channel_id)).strip()
        else:
            raise ConfigValidationError(f"第 {index + 1} 个频道配置无效")

        if not _CHANNEL_ID_RE.fullmatch(channel_id):
            raise ConfigValidationError(f"第 {index + 1} 个频道 ID 无效")
        key = channel_id.lower()
        if key in seen:
            continue
        if len(name) > 100:
            name = name[:100]
        seen.add(key)
        normalized.append({"id": channel_id, "name": name or channel_id})

    if len(normalized) > _MAX_CHANNELS:
        raise ConfigValidationError(f"频道数量不能超过 {_MAX_CHANNELS} 个")
    return normalized


class TelegramResourceSource(ResourceSourceCard):
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
        config_fields=(
            {
                "key": "channels",
                "label": "资源频道",
                "type": "json",
                "default": [],
                "description": "JSON 数组，每项包含频道 id，可选 name。",
            },
            {
                "key": "magic_regex",
                "label": "文件名识别增强",
                "type": "json",
                "default": {},
                "description": "JSON 对象，可配置 pattern 与 replace。",
            },
        ),
    )

    def __init__(self, client: TelegramClient, config_store=None):
        self.client = client
        self.config_store = config_store

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """验证 Telegram 频道与文件名正则，统一通用配置和旧接口规则。"""
        normalized = super().validate_config(config)
        normalized["channels"] = _normalize_channels(normalized.get("channels", []))
        magic_regex = normalized.get("magic_regex", {})
        if magic_regex is None:
            magic_regex = {}
        if not isinstance(magic_regex, dict):
            raise ConfigValidationError("magic_regex 必须是 JSON 对象")
        pattern = str(magic_regex.get("pattern") or "").strip()
        replacement = str(magic_regex.get("replace") or "")
        if len(pattern) > 1000 or len(replacement) > 200:
            raise ConfigValidationError("文件名正则或替换规则过长")
        try:
            if pattern:
                re.compile(pattern)
        except re.error as exc:
            raise ConfigValidationError(f"文件名正则无效：{exc}") from exc
        normalized["magic_regex"] = {"pattern": pattern, "replace": replacement}
        return normalized

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


    def is_configured(self, config: dict[str, Any]) -> bool:
        return bool(config.get("channels")) if isinstance(config, dict) else False

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


def create_card(context):
    """Create Telegram card using the injected Telegram client."""
    return TelegramResourceSource(context["telegram"], context.get("config_store"))
