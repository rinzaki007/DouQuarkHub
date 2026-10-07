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
            "quark_cookie": "",
            "default_fid": "0",
            "openlist_url": DEFAULT_OPENLIST_URL,
            "category_fids": deepcopy(DEFAULT_CATEGORY_FIDS),
            "channels": [],
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

        defaults["category_fids"] = {
            **DEFAULT_CATEGORY_FIDS,
            **(defaults.get("category_fids") or {}),
        }

        defaults["channels"] = self._normalize_channels(
            defaults.get("channels", [])
        )

        return defaults

    def get_cookie(self) -> str:
        return str(
            self.load().get("quark_cookie") or ""
        ).strip()

    def get_channels(self) -> list[dict[str, str]]:
        return self.load()["channels"]

    def public(self) -> dict:
        config = self.load()

        config.pop("quark_cookie", None)

        config["has_quark_cookie"] = bool(
            self.get_cookie()
        )

        return config

    def save(self, incoming: dict) -> dict:
        if not isinstance(incoming, dict):
            raise ConfigValidationError(
                "配置必须是 JSON 对象"
            )

        current = self.load()

        if incoming.get("clear_quark_cookie") is True:
            current["quark_cookie"] = ""

        elif "quark_cookie" in incoming:
            cookie = str(
                incoming.get("quark_cookie") or ""
            ).strip()

            if cookie:
                current["quark_cookie"] = cookie

        if "default_fid" in incoming:
            current["default_fid"] = self._normalize_fid(
                incoming["default_fid"],
                "default_fid",
            )

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

        self.store.write(current)

        return current

    def save_channels(
        self,
        channels: object,
    ) -> list[dict[str, str]]:
        normalized = self._normalize_channels(channels)

        current = self.load()
        current["channels"] = normalized

        self.store.write(current)

        return normalized
