"""MovieSync 通用卡片接口与注册表。

卡片是 MovieSync 的可插拔能力单元。Core 只认识卡片的身份、类型和能力，
不要求卡片必须是 Telegram、夸克或某一种具体实现。

当前版本只建立稳定的接口层，不负责动态安装第三方代码。
"""

from __future__ import annotations

import logging
import re
from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from typing import Any
from urllib.parse import urlparse

from .clients.quark import QuarkClient, sanitize_pwd_id
from .config_store import ConfigStore, ConfigValidationError
from .regex_safety import has_nested_unbounded_quantifier
from .settings import DEFAULT_CATEGORY_FIDS

CARD_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")

CARD_TYPES = {
    "resource_source",
    "storage_target",
    "metadata_provider",
    "notification",
    "automation",
    "custom",
}


@dataclass(frozen=True)
class CardManifest:
    """描述一张卡片的公开身份与能力。"""

    id: str
    name: str
    version: str = "1.0.0"
    type: str = "custom"
    description: str = ""
    capabilities: tuple[str, ...] = ()
    config_version: int = 1
    config_fields: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if not CARD_ID_RE.fullmatch(self.id):
            raise ValueError(f"卡片 ID 无效: {self.id}")
        if self.type not in CARD_TYPES:
            raise ValueError(f"卡片类型无效: {self.type}")
        keys = [str(field.get("key") or "") for field in self.config_fields]
        if any(not key for key in keys) or len(keys) != len(set(keys)):
            raise ValueError("卡片配置字段必须具有唯一且非空的 key")
        allowed_field_types = {"string", "password", "textarea", "boolean", "number", "json"}
        text_field_types = {"string", "password", "textarea"}
        for field in self.config_fields:
            field_type = field.get("type", "string")
            if field_type not in allowed_field_types:
                raise ValueError(f"不支持的配置字段类型: {field_type}")

            for bound in ("min_length", "max_length"):
                value = field.get(bound)
                if value is not None and (
                    isinstance(value, bool) or not isinstance(value, int) or value < 0
                ):
                    raise ValueError(f"配置字段「{field.get('label') or field.get('key')}」的 {bound} 必须是非负整数")

            min_length = field.get("min_length")
            max_length = field.get("max_length")
            if min_length is not None and max_length is not None and min_length > max_length:
                raise ValueError(f"配置字段「{field.get('label') or field.get('key')}」的最小长度不能大于最大长度")

            pattern = field.get("pattern")
            if pattern is not None:
                if field_type not in text_field_types or not isinstance(pattern, str):
                    raise ValueError("pattern 只能用于文本字段，且必须是字符串")
                if len(pattern) > 500:
                    label = field.get("label") or field.get("key")
                    raise ValueError(
                        f"配置字段「{label}」的正则规则不能超过 500 个字符"
                    )
                if has_nested_unbounded_quantifier(pattern):
                    raise ValueError(
                        f"配置字段「{field.get('label') or field.get('key')}」的正则规则包含不安全的嵌套重复"
                    )
                try:
                    re.compile(pattern)
                except re.error as exc:
                    raise ValueError(f"配置字段「{field.get('label') or field.get('key')}」的正则规则无效") from exc

            value_format = field.get("format")
            if value_format is not None:
                if field_type not in text_field_types or value_format not in {"url", "email"}:
                    raise ValueError(f"配置字段「{field.get('label') or field.get('key')}」的格式规则无效")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "type": self.type,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "config_version": self.config_version,
            "config_fields": deepcopy(list(self.config_fields)),
        }


class Card:
    """所有 MovieSync 卡片的最小统一接口。

    卡片可以提供任意能力，但必须明确自己的身份、类型和 capabilities。
    具体业务接口由卡片类型继续扩展，例如 ResourceSource。
    """

    manifest = CardManifest(
        id="unknown",
        name="未命名卡片",
    )

    def check(self, config: dict) -> dict[str, Any]:
        """检查卡片当前是否可用。默认实现表示无需检查。"""
        return {
            "status": "healthy",
            "message": "卡片可用",
        }

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """校验并返回规范化后的完整配置；具体卡片可覆盖业务规则。

        Manifest 可为文本字段声明 min_length、max_length、pattern 或 format
        （目前支持 url、email），供通用卡片配置接口执行一致的基础校验。
        """
        if not isinstance(config, dict):
            raise ConfigValidationError("卡片配置必须是 JSON 对象")

        normalized = deepcopy(config)
        for field in self.manifest.config_fields:
            key = str(field.get("key") or "")
            if key not in normalized or normalized[key] is None:
                continue

            field_type = field.get("type", "string")
            value = normalized[key]
            label = str(field.get("label") or key)

            if field_type in {"string", "password", "textarea"}:
                if not isinstance(value, str):
                    raise ConfigValidationError(f"配置字段「{label}」必须是文本")
                min_length = field.get("min_length")
                max_length = field.get("max_length")
                if min_length is not None and len(value) < min_length:
                    raise ConfigValidationError(
                        f"配置字段「{label}」长度不能少于 {min_length} 个字符"
                    )
                if max_length is not None and len(value) > max_length:
                    raise ConfigValidationError(
                        f"配置字段「{label}」长度不能超过 {max_length} 个字符"
                    )

                pattern = field.get("pattern")
                if pattern:
                    # Python's re engine has no match timeout. Keep generic card
                    # fields bounded even when a plugin omitted max_length.
                    if len(value) > 4096:
                        raise ConfigValidationError(
                            f"配置字段「{label}」用于正则校验的内容不能超过 4096 个字符"
                        )
                    if has_nested_unbounded_quantifier(str(pattern)):
                        raise ConfigValidationError(
                            f"配置字段「{label}」的正则规则包含不安全的嵌套重复"
                        )
                    try:
                        matches = re.fullmatch(str(pattern), value) is not None
                    except re.error as exc:
                        raise ConfigValidationError(
                            f"配置字段「{label}」的格式规则无效"
                        ) from exc
                    if not matches:
                        raise ConfigValidationError(
                            f"配置字段「{label}」格式不正确"
                        )

                value_format = field.get("format")
                if value_format == "url":
                    try:
                        parsed = urlparse(value)
                        hostname = parsed.hostname
                        # Accessing .port validates malformed and out-of-range ports.
                        port = parsed.port
                        valid_url = (
                            parsed.scheme in {"http", "https"}
                            and bool(hostname)
                            and not any(char.isspace() for char in hostname or "")
                            and (port is None or 1 <= port <= 65535)
                        )
                    except ValueError:
                        valid_url = False
                    if not valid_url:
                        raise ConfigValidationError(
                            f"配置字段「{label}」必须是有效的 HTTP 或 HTTPS 地址"
                        )
                elif value_format == "email":
                    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
                        raise ConfigValidationError(
                            f"配置字段「{label}」必须是有效的邮箱地址"
                        )
                elif value_format:
                    raise ConfigValidationError(
                        f"配置字段「{label}」使用了不支持的格式规则: {value_format}"
                    )

        return normalized

    def close(self) -> None:
        """应用退出时释放卡片资源。默认无需处理。"""
        return None

    @property
    def card_id(self) -> str:
        return self.manifest.id

    @property
    def card_type(self) -> str:
        return self.manifest.type

    @property
    def capabilities(self) -> tuple[str, ...]:
        return self.manifest.capabilities


class ResourceSourceCard(Card):
    """资源发现卡片接口。"""

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

    def public_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """返回可给管理界面展示的配置；默认递归隐藏疑似凭据字段。"""
        sensitive = ("cookie", "token", "secret", "password", "api_key", "authorization", "credential", "private_key")

        def sanitize(value):
            if isinstance(value, dict):
                result = {}
                for key, item in value.items():
                    if any(marker in str(key).lower() for marker in sensitive):
                        result[f"has_{key}"] = bool(item)
                    else:
                        result[key] = sanitize(item)
                return result
            if isinstance(value, list):
                return [sanitize(item) for item in value]
            return value

        return sanitize(config if isinstance(config, dict) else {})

    def search_channel(self, channel: object, title: str, config: dict) -> list[dict[str, Any]]:
        """在指定资源源频道中搜索资源；没有频道级能力的卡片返回空列表。"""
        return []


class StorageTargetCard(Card):
    """存储/转存目标卡片接口。"""

    manifest = CardManifest(
        id="unknown.storage",
        name="未命名存储目标",
        type="storage_target",
        capabilities=(
            "storage.check",
            "storage.resolve_resource",
            "storage.list_files",
            "storage.create_folder",
            "storage.transfer",
        ),
    )

    def resolve_resource(self, resource: object) -> dict[str, Any]:
        """解析一个资源并返回可供核心业务使用的标准结果。"""
        raise NotImplementedError

    def list_files(self, resource: object) -> list[dict[str, Any]]:
        raise NotImplementedError

    def destination_options(self) -> list[dict[str, Any]]:
        return []

    def create_folder(self, name: str, parent_id: str = "0") -> str:
        raise NotImplementedError

    def transfer(
        self,
        resource: object,
        files: list[dict[str, Any]],
        target_id: str = "0",
    ) -> tuple[bool, str]:
        raise NotImplementedError


class QuarkStorageCard(StorageTargetCard):
    """内置夸克存储卡。

    这里只负责把现有 QuarkClient 包装成标准 StorageTargetCard；
    原有 QuarkClient 业务保持不变，降低迁移风险。
    """

    manifest = CardManifest(
        id="quark",
        name="Quark",
        version="1.0.0",
        type="storage_target",
        description="夸克网盘存储与转存卡片",
        capabilities=(
            "storage.check",
            "storage.resolve_resource",
            "storage.list_files",
            "storage.create_folder",
            "storage.transfer",
        ),
        config_fields=(
            {
                "key": "cookie",
                "label": "夸克 Cookie",
                "type": "password",
                "secret": True,
                "required": False,
                "placeholder": "粘贴 Cookie；留空则保留已保存的值",
                "description": "敏感凭据不会回显到页面。",
            },
            {
                "key": "default_fid",
                "label": "默认目录 FID",
                "type": "string",
                "required": True,
                "default": "0",
                "placeholder": "0",
            },
            {
                "key": "category_fids",
                "label": "分类目录 FID",
                "type": "json",
                "default": {},
                "description": "JSON 对象，例如电影和电视剧对应的目录 FID。",
            },
        ),
    )

    def __init__(self, config_store):
        self.config_store = config_store

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """验证夸克目录配置，避免通用表单绕过专用接口的 FID 校验。"""
        normalized = super().validate_config(config)
        normalized["default_fid"] = ConfigStore._normalize_fid(
            normalized.get("default_fid", "0"), "cards.quark.config.default_fid"
        )
        category_fids = normalized.get("category_fids", {})
        if category_fids is None:
            category_fids = {}
        if not isinstance(category_fids, dict):
            raise ConfigValidationError("Quark 分类目录 FID 必须是对象")
        unknown = set(category_fids) - set(DEFAULT_CATEGORY_FIDS)
        if unknown:
            raise ConfigValidationError("未知分类目录: " + ", ".join(sorted(map(str, unknown))))
        normalized["category_fids"] = {
            key: ConfigStore._normalize_fid(
                category_fids.get(key, ""),
                f"cards.quark.config.category_fids.{key}",
                allow_empty=True,
            )
            for key in DEFAULT_CATEGORY_FIDS
        }
        return normalized

    def destination_options(self) -> list[dict[str, Any]]:
        config = self.config_store.get_quark_config()
        options = []
        default_fid = str(config.get("default_fid") or "0")
        options.append({"id": default_fid, "name": "默认目录", "is_default": True})
        for name, fid in (config.get("category_fids") or {}).items():
            fid = str(fid or "").strip()
            if fid:
                options.append({
                    "id": fid,
                    "name": f"{name}目录",
                    "category": name,
                    "is_default": False,
                })
        seen = set()
        return [item for item in options if not (item["id"] in seen or seen.add(item["id"]))]


    def _client(self) -> QuarkClient:
        return QuarkClient(self.config_store.get_cookie())

    def check(self, config: dict | None = None) -> dict[str, Any]:
        cookie = self.config_store.get_cookie()
        if not cookie:
            return {
                "status": "unconfigured",
                "message": "尚未配置夸克 Cookie",
            }
        valid = self._client().check_cookie_valid()
        return {
            "status": "healthy" if valid else "unavailable",
            "message": "夸克 Cookie 有效" if valid else "夸克 Cookie 无效或已过期",
        }

    def resolve_resource(self, resource: object) -> dict[str, Any]:
        if not isinstance(resource, dict):
            return {"files": [], "token": None, "error": "资源参数无效"}
        pwd_id = sanitize_pwd_id(resource.get("pwd_id"))
        if not pwd_id:
            return {"files": [], "token": None, "error": "分享资源 ID 无效"}
        files, stoken, error = self._client().get_share_files(pwd_id)
        return {
            "files": files or [],
            "token": stoken,
            "error": error,
        }

    def list_files(self, resource: object) -> list[dict[str, Any]]:
        return self.resolve_resource(resource).get("files") or []

    def create_folder(self, name: str, parent_id: str = "0") -> str:
        fid, error = self._client().get_or_create_subfolder(name, parent_id)
        if not fid:
            raise RuntimeError(error or "创建目录失败")
        return fid

    def transfer(
        self,
        resource: object,
        files: list[dict[str, Any]],
        target_id: str = "0",
    ) -> tuple[bool, str]:
        if not isinstance(resource, dict):
            return False, "资源参数无效"
        pwd_id = sanitize_pwd_id(resource.get("pwd_id"))
        stoken = resource.get("stoken")
        if not pwd_id or not stoken:
            return False, "分享资源参数无效"
        return self._client().save_files(
            pwd_id,
            files,
            stoken,
            target_id,
        )


class NotificationCard(Card):
    """通知通道卡片接口。

    核心只提交标准化事件和负载；具体通知平台、鉴权和投递方式由卡片实现。
    """

    manifest = CardManifest(
        id="unknown.notification",
        name="未命名通知通道",
        type="notification",
        capabilities=("notification.send",),
    )

    def send(
        self,
        event: str,
        payload: dict[str, Any],
        config: dict[str, Any],
    ) -> bool:
        """发送一条通知；返回 True 表示卡片确认已接受该通知。"""
        raise NotImplementedError


class MetadataProviderCard(Card):
    """影视/媒体元数据卡片接口。"""

    manifest = CardManifest(
        id="unknown.metadata",
        name="未命名元数据源",
        type="metadata_provider",
        capabilities=("metadata.list", "metadata.search", "metadata.detail"),
    )

    def list_movies(self, tag: str, sort_type: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def search(self, query: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def get_detail(self, item_id: str) -> dict[str, Any] | None:
        raise NotImplementedError


class NotificationCard(Card):
    """通知卡片接口。"""

    manifest = CardManifest(
        id="unknown.notification",
        name="未命名通知服务",
        type="notification",
        capabilities=("notification.send",),
    )

    def send(self, message: str, **kwargs: Any) -> bool:
        raise NotImplementedError


class CardRegistry:
    """进程内卡片注册表。

    Registry 只负责发现和管理已经加载的卡片实例，不负责持久化配置，
    也不负责下载/执行第三方代码。这样即使未来某张卡片不可用，
    Core 仍然可以继续运行其它卡片。
    """

    def __init__(self):
        self._cards: dict[str, Card] = {}
        self.lock = RLock()

    def _close_card(self, card: Card) -> None:
        """释放卡片资源；单张卡片的清理失败不应影响注册表操作。"""
        try:
            card.close()
        except Exception:
            logging.getLogger(__name__).exception(
                "关闭卡片 %s 失败",
                card.card_id,
            )

    def register(self, card: Card, *, replace: bool = False) -> Card:
        if not isinstance(card, Card):
            raise TypeError("只能注册 Card 实例")

        card_id = card.card_id
        with self.lock:
            previous = self._cards.get(card_id)
            if previous is not None and not replace:
                raise ValueError(f"卡片已注册: {card_id}")
            self._cards[card_id] = card

        # Do not call third-party cleanup code while holding the registry lock.
        if previous is not None and previous is not card:
            self._close_card(previous)
        return card

    def unregister(self, card_id: str) -> Card | None:
        with self.lock:
            card = self._cards.pop(str(card_id), None)
        if card is not None:
            self._close_card(card)
        return card

    def close_all(self) -> None:
        """移除并关闭全部已注册卡片，逐张隔离清理异常。"""
        with self.lock:
            cards = list(self._cards.values())
            self._cards.clear()

        for card in cards:
            self._close_card(card)

    def get(self, card_id: str) -> Card | None:
        with self.lock:
            return self._cards.get(str(card_id))

    def list(self) -> list[Card]:
        with self.lock:
            return list(self._cards.values())

    def manifests(self) -> list[dict[str, Any]]:
        with self.lock:
            return [card.manifest.to_dict() for card in self._cards.values()]

    def find_by_type(self, card_type: str) -> list[Card]:
        with self.lock:
            return [
                card
                for card in self._cards.values()
                if card.card_type == card_type
            ]

    def find_by_capability(self, capability: str) -> list[Card]:
        with self.lock:
            return [
                card
                for card in self._cards.values()
                if capability in card.capabilities
            ]


