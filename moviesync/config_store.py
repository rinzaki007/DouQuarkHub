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
CONFIG_SCHEMA_VERSION = 5


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
            },
            "openlist_url": DEFAULT_OPENLIST_URL,
            "default_storage_target_id": "",
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

        if not url:
            return ""

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
        if "quark_cookie" in defaults:
            quark_config["cookie"] = str(defaults.get("quark_cookie") or "")
        if "default_fid" in defaults:
            quark_config["default_fid"] = defaults.get("default_fid") or "0"
        if "category_fids" in defaults:
            quark_config["category_fids"] = deepcopy(
                defaults.get("category_fids") or DEFAULT_CATEGORY_FIDS
            )
        quark["enabled"] = bool(quark.get("enabled", True))
        quark["config"] = quark_config
        cards["quark"] = quark

        telegram = cards.get("telegram") if isinstance(cards.get("telegram"), dict) else {}
        telegram_config = telegram.get("config") if isinstance(telegram.get("config"), dict) else {}
        if not isinstance(telegram_config.get("magic_regex"), dict):
            telegram_config["magic_regex"] = deepcopy(
                self._defaults()["cards"]["telegram"]["config"]["magic_regex"]
            )
        if "channels" in defaults and not telegram_config.get("channels"):
            telegram_config["channels"] = defaults.get("channels") or []
        old_sources = defaults.get("resource_sources")
        source = next(
            (item for item in old_sources if isinstance(item, dict) and item.get("id") == "telegram"),
            None,
        ) if isinstance(old_sources, list) else None
        if source:
            telegram["enabled"] = bool(source.get("enabled", telegram.get("enabled", True)))
            if source.get("health"):
                telegram_config["health"] = dict(source["health"])
        telegram["enabled"] = bool(telegram.get("enabled", True))
        telegram_config["channels"] = self._normalize_channels(
            telegram_config.get("channels", [])
        )
        health = dict(self._defaults()["cards"]["telegram"]["config"]["health"])
        health.update(telegram_config.get("health") or {})
        telegram_config["health"] = health
        telegram["config"] = telegram_config
        cards["telegram"] = telegram

        defaults["cards"] = cards
        for key in ("quark_cookie", "default_fid", "category_fids", "channels", "resource_sources"):
            defaults.pop(key, None)

        try:
            schema_version = int(defaults.get("schema_version", 1))
        except (TypeError, ValueError):
            schema_version = 1
        defaults["schema_version"] = max(schema_version, CONFIG_SCHEMA_VERSION)

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
        return defaults

    def save_card_config(
        self,
        card_id: str,
        incoming: dict,
        *,
        enabled: bool | None = None,
    ) -> dict:
        """保存已注册卡片的通用配置；调用方必须先确认卡片已加载。"""
        card_id = str(card_id or "").strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", card_id):
            raise ConfigValidationError("卡片 ID 无效")
        if not isinstance(incoming, dict):
            raise ConfigValidationError("卡片配置必须是 JSON 对象")
        current = self.load()
        cards = current.setdefault("cards", {})
        saved = cards.get(card_id)
        saved = saved if isinstance(saved, dict) else {}
        config = saved.get("config")
        config = dict(config) if isinstance(config, dict) else {}
        config.update(deepcopy(incoming))
        saved["config"] = config
        if enabled is not None:
            saved["enabled"] = bool(enabled)
        else:
            saved["enabled"] = bool(saved.get("enabled", True))
        cards[card_id] = saved
        current["cards"] = cards
        current["schema_version"] = CONFIG_SCHEMA_VERSION
        self.store.write(current)
        return deepcopy(saved)

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

    def get_default_storage_target_id(self) -> str:
        return str(self.load().get("default_storage_target_id") or "").strip()

    def set_default_storage_target_id(self, target_id: object) -> str:
        target_id = str(target_id or "").strip()
        if len(target_id) > 64 or (target_id and not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", target_id)):
            raise ConfigValidationError("默认存储目标 ID 无效")
        current = self.load()
        current["default_storage_target_id"] = target_id
        current["schema_version"] = CONFIG_SCHEMA_VERSION
        self.store.write(current)
        return target_id

    def get_channels(self) -> list[dict[str, str]]:
        return self.load()["cards"]["telegram"]["config"]["channels"]

    def get_telegram_config(self) -> dict:
        return deepcopy(self.load()["cards"]["telegram"]["config"])

    def save_telegram_config(self, incoming: dict) -> dict:
        if not isinstance(incoming, dict):
            raise ConfigValidationError("Telegram 卡片配置必须是 JSON 对象")
        current = self.load()
        card = current["cards"]["telegram"]
        config = card["config"]
        if "channels" in incoming:
            config["channels"] = self._normalize_channels(incoming["channels"])
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
            config["magic_regex"] = {"pattern": pattern, "replace": replacement}
        if "enabled" in incoming:
            card["enabled"] = bool(incoming["enabled"])
        current["cards"]["telegram"] = card
        current["schema_version"] = CONFIG_SCHEMA_VERSION
        self.store.write(current)
        return deepcopy(card)

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
        if "default_storage_target_id" in incoming:
            target_id = str(incoming.get("default_storage_target_id") or "").strip()
            if len(target_id) > 64 or (target_id and not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", target_id)):
                raise ConfigValidationError("默认存储目标 ID 无效")
            current["default_storage_target_id"] = target_id

        imported_cards = incoming.get("cards")
        if isinstance(imported_cards, dict):
            if isinstance(imported_cards.get("quark"), dict):
                quark = imported_cards["quark"]
                quark_config = quark.get("config")
                if isinstance(quark_config, dict):
                    imported_quark = dict(quark_config)
                    if "cookie" in imported_quark:
                        cookie = str(imported_quark.pop("cookie") or "").strip()
                        imported_quark["clear_cookie"] = not bool(cookie)
                        if cookie:
                            imported_quark["cookie"] = cookie
                    self.save_quark_config(imported_quark)
                current = self.load()
                if "enabled" in quark:
                    current["cards"]["quark"]["enabled"] = bool(quark["enabled"])
                    self.store.write(current)
            if isinstance(imported_cards.get("telegram"), dict):
                telegram = imported_cards["telegram"]
                telegram_config = telegram.get("config")
                if isinstance(telegram_config, dict):
                    self.save_telegram_config({
                        key: value
                        for key, value in telegram_config.items()
                        if key in {"channels", "magic_regex"}
                    })
                current = self.load()
                if "enabled" in telegram:
                    current["cards"]["telegram"]["enabled"] = bool(telegram["enabled"])
                    self.store.write(current)

        if "channels" in incoming:
            self.save_telegram_config({"channels": incoming["channels"]})
            current = self.load()

        current["schema_version"] = CONFIG_SCHEMA_VERSION
        self.store.write(current)

        return current

    def get_resource_sources(self) -> list[dict]:
        config = self.get_telegram_config()
        card = self.load()["cards"]["telegram"]
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
        current = self.load()
        import time

        now = time.time()
        if source_id != "telegram":
            return
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
        self.store.write(current)

    def save_channels(
        self,
        channels: object,
    ) -> list[dict[str, str]]:
        return self.save_telegram_config({"channels": channels})["config"]["channels"]
