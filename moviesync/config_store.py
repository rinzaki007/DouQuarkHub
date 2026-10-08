"""MovieSync 持久化配置管理。

用途：管理夸克 Cookie、默认/分类 FID、OpenList 地址和 Telegram 频道，并校验外部输入。
维护说明：统一配置写入 data/config.json；对外 public() 会主动隐藏夸克 Cookie。
"""
from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse

from .settings import DEFAULT_CATEGORY_FIDS, DEFAULT_OPENLIST_URL
from .storage import JsonStore

CHANNEL_ID_RE = re.compile(r"^[A-Za-z0-9_]{2,64}$")
FID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

MAX_CHANNELS = 100
CONFIG_SCHEMA_VERSION = 3


class ConfigValidationError(ValueError):
    pass


class ConfigStore:
    def __init__(self, config_file: Path, legacy_root: Path):
        self.store = JsonStore(config_file, self._defaults)
        self.legacy_root = legacy_root
        self._migrate_legacy()

    @staticmethod
    def _defaults() -> dict:
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
            },
            "openlist_url": DEFAULT_OPENLIST_URL,
            "channels": [],
            "resource_sources": [
                {
                    "id": "telegram",
                    "name": "Telegram",
                    "type": "telegram",
                    "enabled": True,
                    "health": {
                        "status": "unknown",
                        "message": "尚未检查",
                        "last_checked_at": None,
                        "last_success_at": None,
                        "failure_count": 0,
                    },
                }
            ],
            "schema_version": CONFIG_SCHEMA_VERSION,
        }

    def _migrate_legacy(self) -> None:
        current = self.store.read()
        legacy_config = self.legacy_root / "config.json"
        legacy_channels = [
            self.legacy_root / "channels.json",
            self.store.path.parent / "channels.json",
        ]

        if self.store.path.exists():
            return

        if legacy_config.exists():
            try:
                import json

                incoming = json.loads(
                    legacy_config.read_text(encoding="utf-8")
                )

                if isinstance(incoming, dict):
                    current.update(incoming)
            except (OSError, ValueError):
                pass

        if not current.get("channels"):
            for channel_path in legacy_channels:
                if not channel_path.exists():
                    continue

                try:
                    import json

                    channels = json.loads(
                        channel_path.read_text(encoding="utf-8")
                    )

                    if isinstance(channels, list):
                        current["channels"] = channels

                    break
                except (OSError, ValueError):
                    continue

        self.store.write(current)

    @staticmethod
    def _normalize_fid(
        value: object,
        field: str,
        *,
        allow_empty: bool = False,
    ) -> str:
        fid = str(value or "").strip()

        if not fid:
            if allow_empty:
                return ""
            return "0"

        if not FID_RE.fullmatch(fid):
            raise ConfigValidationError(f"{field} 格式无效")

        return fid

    @staticmethod
    def _normalize_channels(
        channels: object,
    ) -> list[dict[str, str]]:
        if channels is None:
            return []

        if not isinstance(channels, list):
            raise ConfigValidationError("channels 必须是数组")

        result: list[dict[str, str]] = []
        seen: set[str] = set()

        for index, item in enumerate(channels):
            if isinstance(item, str):
                channel_id = item.strip().lstrip("@")
                name = channel_id

            elif isinstance(item, dict):
                channel_id = str(
                    item.get("id", "")
                ).strip().lstrip("@")

                name = str(
                    item.get("name", channel_id)
                ).strip()

            else:
                raise ConfigValidationError(
                    f"第 {index + 1} 个频道配置无效"
                )

            if not CHANNEL_ID_RE.fullmatch(channel_id):
                raise ConfigValidationError(
                    f"第 {index + 1} 个频道 ID 无效"
                )

            key = channel_id.lower()

            if key in seen:
                continue

            if len(name) > 100:
                name = name[:100]

            seen.add(key)

            result.append(
                {
                    "id": channel_id,
                    "name": name or channel_id,
                }
            )

        if len(result) > MAX_CHANNELS:
            raise ConfigValidationError(
                f"频道数量不能超过 {MAX_CHANNELS} 个"
            )

        return result

    @staticmethod
    def _normalize_openlist(value: object) -> str:
        url = str(
            value or DEFAULT_OPENLIST_URL
        ).strip()

        parsed = urlparse(url)

        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConfigValidationError("OpenList 地址无效")

        return url

    def load(self) -> dict:
        data = self.store.read()

        defaults = self._defaults()

        if isinstance(data, dict):
            defaults.update(data)

        cards = defaults.get("cards") if isinstance(defaults.get("cards"), dict) else {}
        quark = cards.get("quark") if isinstance(cards.get("quark"), dict) else {}
        quark_config = quark.get("config") if isinstance(quark.get("config"), dict) else {}
        if "quark_cookie" in defaults and "cookie" not in quark_config:
            quark_config["cookie"] = str(defaults.get("quark_cookie") or "")
        if "default_fid" in defaults and "default_fid" not in quark_config:
            quark_config["default_fid"] = defaults.get("default_fid") or "0"
        if "category_fids" in defaults and "category_fids" not in quark_config:
            quark_config["category_fids"] = deepcopy(defaults.get("category_fids") or DEFAULT_CATEGORY_FIDS)
        quark["enabled"] = bool(quark.get("enabled", True))
        quark["config"] = quark_config
        cards["quark"] = quark
        defaults["cards"] = cards

        # 旧版本没有 schema_version；读取时自动补齐，后续保存即完成升级。
        try:
            schema_version = int(
                defaults.get("schema_version", 1)
            )
        except (TypeError, ValueError):
            schema_version = 1

        defaults["schema_version"] = max(
            schema_version,
            CONFIG_SCHEMA_VERSION,
        )

        quark_config = defaults["cards"]["quark"].setdefault("config", {})
        quark_config["default_fid"] = self._normalize_fid(
            quark_config.get("default_fid", "0"),
            "cards.quark.config.default_fid",
        )
        incoming_category_fids = quark_config.get("category_fids") or {}
        quark_config["category_fids"] = {
            key: self._normalize_fid(
                incoming_category_fids.get(key, ""),
                f"cards.quark.config.category_fids.{key}",
                allow_empty=True,
            )
            for key in DEFAULT_CATEGORY_FIDS
        }

        defaults["channels"] = self._normalize_channels(
            defaults.get("channels", [])
        )

        source_defaults = self._defaults()["resource_sources"]
        incoming_sources = defaults.get("resource_sources") or []
        source_map = {
            str(item.get("id")): item
            for item in incoming_sources
            if isinstance(item, dict) and item.get("id")
        }
        defaults["resource_sources"] = []
        for source in source_defaults:
            item = dict(source)
            saved = source_map.get(source["id"], {})
            item["enabled"] = bool(saved.get("enabled", item["enabled"]))
            health = dict(item["health"])
            health.update(saved.get("health") or {})
            item["health"] = health
            defaults["resource_sources"].append(item)

        return defaults

    def get_quark_config(self) -> dict:
        return deepcopy(self.load()["cards"]["quark"]["config"])

    def save_quark_config(self, incoming: dict) -> dict:
        if not isinstance(incoming, dict):
            raise ConfigValidationError("Quark 卡片配置必须是 JSON 对象")
        current = self.load()
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
            config["default_fid"] = self._normalize_fid(
                incoming["default_fid"],
                "cards.quark.config.default_fid",
            )
        if "category_fids" in incoming:
            category_fids = incoming["category_fids"] or {}
            if not isinstance(category_fids, dict):
                raise ConfigValidationError("Quark 分类目录 FID 必须是对象")
            config["category_fids"] = {
                key: self._normalize_fid(
                    category_fids.get(key, config["category_fids"].get(key, "")),
                    f"cards.quark.config.category_fids.{key}",
                    allow_empty=True,
                )
                for key in DEFAULT_CATEGORY_FIDS
            }
        current["cards"]["quark"] = quark
        current["schema_version"] = CONFIG_SCHEMA_VERSION
        self.store.write(current)
        return deepcopy(quark)

    def get_cookie(self) -> str:
        return str(
            self.get_quark_config().get("cookie") or ""
        ).strip()

    def get_channels(self) -> list[dict[str, str]]:
        return self.load()["channels"]

    def public(self) -> dict:
        config = self.load()

        quark = config["cards"]["quark"]
        quark_config = quark["config"]
        quark["config"] = {
            **quark_config,
            "cookie": "",
            "has_cookie": bool(quark_config.get("cookie")),
        }
        return config

    def save(self, incoming: dict) -> dict:
        if not isinstance(incoming, dict):
            raise ConfigValidationError(
                "配置必须是 JSON 对象"
            )

        current = self.load()

        legacy_quark = {}
        if incoming.get("clear_quark_cookie") is True:
            legacy_quark["clear_cookie"] = True
        elif "quark_cookie" in incoming:
            legacy_quark["cookie"] = incoming.get("quark_cookie")
        if "default_fid" in incoming:
            legacy_quark["default_fid"] = incoming["default_fid"]
        if "category_fids" in incoming:
            legacy_quark["category_fids"] = incoming["category_fids"]
        if legacy_quark:
            self.save_quark_config(legacy_quark)
            current = self.load()

        if "openlist_url" in incoming:
            current["openlist_url"] = self._normalize_openlist(
                incoming["openlist_url"]
            )

        if "category_fids" in incoming:
            category_fids = incoming["category_fids"] or {}

            if not isinstance(category_fids, dict):
                raise ConfigValidationError(
                    "category_fids 必须是对象"
                )

            current["category_fids"] = {
                key: self._normalize_fid(
                    category_fids.get(
                        key,
                        current["category_fids"].get(key, ""),
                    ),
                    f"category_fids.{key}",
                    allow_empty=True,
                )
                for key in DEFAULT_CATEGORY_FIDS
            }

        if "channels" in incoming:
            current["channels"] = self._normalize_channels(
                incoming["channels"]
            )

        if "resource_sources" in incoming:
            source_items = incoming["resource_sources"]
            if not isinstance(source_items, list):
                raise ConfigValidationError("resource_sources 必须是数组")
            normalized_sources = []
            for item in source_items:
                if not isinstance(item, dict):
                    raise ConfigValidationError("资源源配置无效")
                source_id = str(item.get("id") or "").strip().lower()
                if source_id != "telegram":
                    continue
                normalized_sources.append({
                    "id": "telegram",
                    "name": "Telegram",
                    "type": "telegram",
                    "enabled": bool(item.get("enabled", True)),
                    "health": current["resource_sources"][0].get("health", {}),
                })
                break
            if normalized_sources:
                current["resource_sources"] = normalized_sources

        current["schema_version"] = CONFIG_SCHEMA_VERSION
        self.store.write(current)

        return current

    def get_resource_sources(self) -> list[dict]:
        return self.load().get("resource_sources", [])

    def update_resource_source_health(
        self,
        source_id: str,
        status: str,
        message: str,
        channels: list[dict] | None = None,
    ) -> None:
        current = self.load()
        import time

        now = time.time()
        for item in current.get("resource_sources", []):
            if item.get("id") != source_id:
                continue
            health = item.setdefault("health", {})
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
                health["failure_count"] = int(
                    health.get("failure_count", 0) or 0
                ) + 1
            self.store.write(current)
            return

    def save_channels(
        self,
        channels: object,
    ) -> list[dict[str, str]]:
        normalized = self._normalize_channels(channels)

        current = self.load()
        current["channels"] = normalized

        self.store.write(current)

        return normalized
