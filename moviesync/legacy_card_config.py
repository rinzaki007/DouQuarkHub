"""Compatibility helpers for historical, built-in card configuration.

The generic ConfigStore owns persistence and schema versioning. This module keeps
legacy Quark/Telegram defaults and migrations isolated while old installations
continue to use their existing config.json format.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

from .settings import DEFAULT_CATEGORY_FIDS


def legacy_card_defaults() -> dict[str, Any]:
    """Return defaults required to read existing Quark/Telegram installations."""
    return {
        "cards": {
            "quark": {
                "enabled": True,
                "config": {
                    "cookie": "",
                    "default_fid": "0",
                    "category_fids": deepcopy(DEFAULT_CATEGORY_FIDS),
                },
            },
            "telegram": {
                "enabled": True,
                "config": {
                    "channels": [],
                    "magic_regex": {
                        "pattern": ".*?(?<!\\d)([Ss]\\d{1,2})?([Ee]?[Pp]?[Xx]?\\d{1,3})(?!\\d).*?\\.(mp4|mkv)",
                        "replace": "\\1\\2.\\3",
                    },
                    "health": {
                        "status": "unknown",
                        "message": "尚未检查",
                        "last_checked_at": None,
                        "last_success_at": None,
                        "failure_count": 0,
                        "channels": [],
                    },
                },
            },
        }
    }


def migrate_legacy_files(store, legacy_root: Path) -> None:
    """Import pre-config-store config.json/channels.json files once."""
    current = store.read()
    legacy_config = legacy_root / "config.json"
    legacy_channels = [
        legacy_root / "channels.json",
        store.path.parent / "channels.json",
    ]

    if store.path.exists():
        return

    if legacy_config.exists():
        try:
            incoming = json.loads(legacy_config.read_text(encoding="utf-8"))
            if isinstance(incoming, dict):
                current.update(incoming)
        except (OSError, ValueError):
            pass

    if not current.get("channels"):
        for channel_path in legacy_channels:
            if not channel_path.exists():
                continue
            try:
                channels = json.loads(channel_path.read_text(encoding="utf-8"))
                if isinstance(channels, list):
                    current["channels"] = channels
                break
            except (OSError, ValueError):
                continue

    store.write(current)


def normalize_legacy_card_config(
    data: dict[str, Any],
    *,
    normalize_fid: Callable[..., str],
    normalize_channels: Callable[[object], list[dict[str, str]]],
    default_category_fids: dict[str, str],
    schema_version: int,
) -> dict[str, Any]:
    """Normalize historical Quark/Telegram fields into the generic cards map."""
    cards = data.get("cards") if isinstance(data.get("cards"), dict) else {}
    quark = cards.get("quark") if isinstance(cards.get("quark"), dict) else {}
    quark_config = quark.get("config") if isinstance(quark.get("config"), dict) else {}

    if "quark_cookie" in data:
        quark_config["cookie"] = str(data.get("quark_cookie") or "")
    if "default_fid" in data:
        quark_config["default_fid"] = data.get("default_fid") or "0"
    if "category_fids" in data:
        quark_config["category_fids"] = deepcopy(
            data.get("category_fids") or default_category_fids
        )
    quark["enabled"] = bool(quark.get("enabled", True))
    quark["config"] = quark_config
    cards["quark"] = quark

    telegram = cards.get("telegram") if isinstance(cards.get("telegram"), dict) else {}
    telegram_config = telegram.get("config") if isinstance(telegram.get("config"), dict) else {}
    if not isinstance(telegram_config.get("magic_regex"), dict):
        telegram_config["magic_regex"] = deepcopy(
            legacy_card_defaults()["cards"]["telegram"]["config"]["magic_regex"]
        )
    if "channels" in data and not telegram_config.get("channels"):
        telegram_config["channels"] = data.get("channels") or []

    old_sources = data.get("resource_sources")
    source = next(
        (item for item in old_sources if isinstance(item, dict) and item.get("id") == "telegram"),
        None,
    ) if isinstance(old_sources, list) else None
    if source:
        telegram["enabled"] = bool(source.get("enabled", telegram.get("enabled", True)))
        if source.get("health"):
            telegram_config["health"] = dict(source["health"])

    telegram["enabled"] = bool(telegram.get("enabled", True))
    telegram_config["channels"] = normalize_channels(telegram_config.get("channels", []))
    health = dict(legacy_card_defaults()["cards"]["telegram"]["config"]["health"])
    health.update(telegram_config.get("health") or {})
    telegram_config["health"] = health
    telegram["config"] = telegram_config
    cards["telegram"] = telegram

    data["cards"] = cards
    for key in ("quark_cookie", "default_fid", "category_fids", "channels", "resource_sources"):
        data.pop(key, None)

    try:
        version = int(data.get("schema_version", 1))
    except (TypeError, ValueError):
        version = 1
    data["schema_version"] = max(version, schema_version)

    quark_config = data["cards"]["quark"].setdefault("config", {})
    quark_config["default_fid"] = normalize_fid(
        quark_config.get("default_fid", "0"),
        "cards.quark.config.default_fid",
    )
    incoming_category_fids = quark_config.get("category_fids") or {}
    quark_config["category_fids"] = {
        key: normalize_fid(
            incoming_category_fids.get(key, ""),
            f"cards.quark.config.category_fids.{key}",
            allow_empty=True,
        )
        for key in default_category_fids
    }
    return data


class LegacyCardConfigAdapter:
    """Backward-compatible Quark/Telegram config accessors outside the core store."""

    def __init__(self, config_store, schema_version: int):
        self.config_store = config_store
        self.schema_version = schema_version

    def get_quark_config(self) -> dict:
        return deepcopy(self.config_store.load()["cards"]["quark"]["config"])

    def save_quark_config(self, incoming: dict) -> dict:
        from .errors import ConfigValidationError

        if not isinstance(incoming, dict):
            raise ConfigValidationError("Quark 卡片配置必须是 JSON 对象")
        store = self.config_store
        current = store.load()
        quark = current["cards"]["quark"]
        config = quark["config"]
        if incoming.get("clear_cookie") is True:
            config["cookie"] = ""
        elif "cookie" in incoming:
            cookie = str(incoming.get("cookie") or "").strip()
            if cookie:
                config["cookie"] = cookie
        if "enabled" in incoming:
            quark["enabled"] = bool(incoming["enabled"])
        if "default_fid" in incoming:
            config["default_fid"] = store._normalize_fid(
                incoming["default_fid"],
                "cards.quark.config.default_fid",
            )
        if "category_fids" in incoming:
            category_fids = incoming["category_fids"] or {}
            if not isinstance(category_fids, dict):
                raise ConfigValidationError("Quark 分类目录 FID 必须是对象")
            config["category_fids"] = {
                key: store._normalize_fid(
                    category_fids.get(key, config["category_fids"].get(key, "")),
                    f"cards.quark.config.category_fids.{key}",
                    allow_empty=True,
                )
                for key in DEFAULT_CATEGORY_FIDS
            }
        current["cards"]["quark"] = quark
        current["schema_version"] = self.schema_version
        store.store.write(current)
        return deepcopy(quark)

    def get_cookie(self) -> str:
        return str(self.get_quark_config().get("cookie") or "").strip()

    def get_channels(self) -> list[dict[str, str]]:
        return self.config_store.load()["cards"]["telegram"]["config"]["channels"]

    def get_telegram_config(self) -> dict:
        return deepcopy(self.config_store.load()["cards"]["telegram"]["config"])

    def save_telegram_config(self, incoming: dict) -> dict:
        import re

        from .errors import ConfigValidationError
        from .regex_safety import has_nested_unbounded_quantifier

        if not isinstance(incoming, dict):
            raise ConfigValidationError("Telegram 卡片配置必须是 JSON 对象")
        store = self.config_store
        current = store.load()
        card = current["cards"]["telegram"]
        config = card["config"]
        if "channels" in incoming:
            config["channels"] = store._normalize_channels(incoming["channels"])
        if "magic_regex" in incoming:
            magic_regex = incoming.get("magic_regex")
            if not isinstance(magic_regex, dict):
                raise ConfigValidationError("magic_regex 必须是 JSON 对象")
            pattern = str(magic_regex.get("pattern") or "").strip()
            replacement = str(magic_regex.get("replace") or "")
            if len(pattern) > 1000 or len(replacement) > 200:
                raise ConfigValidationError("文件名正则或替换规则过长")
            try:
                re.compile(pattern) if pattern else None
            except re.error as exc:
                raise ConfigValidationError(f"文件名正则无效：{exc}") from exc
            if pattern and has_nested_unbounded_quantifier(pattern):
                raise ConfigValidationError("文件名正则包含高风险的嵌套无限量词")
            config["magic_regex"] = {"pattern": pattern, "replace": replacement}
        if "enabled" in incoming:
            card["enabled"] = bool(incoming["enabled"])
        current["cards"]["telegram"] = card
        current["schema_version"] = self.schema_version
        store.store.write(current)
        return deepcopy(card)

    def get_resource_sources(self) -> list[dict]:
        config = self.get_telegram_config()
        card = self.config_store.load()["cards"]["telegram"]
        return [{
            "id": "telegram",
            "name": "Telegram",
            "type": "telegram",
            "enabled": bool(card.get("enabled", True)),
            "health": config.get("health", {}),
        }]

    def update_resource_source_health(
        self,
        source_id: str,
        status: str,
        message: str,
        channels: list[dict] | None = None,
    ) -> None:
        import time

        if source_id != "telegram":
            return
        store = self.config_store
        current = store.load()
        now = time.time()
        card = current["cards"]["telegram"]
        health = card["config"].setdefault("health", {})
        health["status"] = str(status or "unknown")
        health["message"] = str(message or "")[:200]
        health["last_checked_at"] = now
        if channels is not None:
            health["channels"] = [
                {
                    "id": str(channel.get("id") or ""),
                    "name": str(channel.get("name") or ""),
                    "status": str(channel.get("status") or "unknown"),
                    "message": str(channel.get("message") or "")[:200],
                }
                for channel in channels
                if isinstance(channel, dict)
            ]
        if status == "healthy":
            health["last_success_at"] = now
        elif status == "unavailable":
            health["failure_count"] = int(health.get("failure_count", 0) or 0) + 1
        store.store.write(current)

    def save_channels(self, channels: object) -> list[dict[str, str]]:
        return self.save_telegram_config({"channels": channels})["config"]["channels"]
