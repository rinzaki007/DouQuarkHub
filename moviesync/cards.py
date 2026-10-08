"""MovieSync 通用卡片接口与注册表。

卡片是 MovieSync 的可插拔能力单元。Core 只认识卡片的身份、类型和能力，
不要求卡片必须是 Telegram、夸克或某一种具体实现。

当前版本只建立稳定的接口层，不负责动态安装第三方代码。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from threading import RLock
from typing import Any

from .clients.quark import QuarkClient, sanitize_pwd_id

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

    def __post_init__(self) -> None:
        if not CARD_ID_RE.fullmatch(self.id):
            raise ValueError(f"卡片 ID 无效: {self.id}")
        if self.type not in CARD_TYPES:
            raise ValueError(f"卡片类型无效: {self.type}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "type": self.type,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "config_version": self.config_version,
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
    )

    def __init__(self, config_store):
        self.config_store = config_store

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

    def register(self, card: Card, *, replace: bool = False) -> Card:
        if not isinstance(card, Card):
            raise TypeError("只能注册 Card 实例")

        card_id = card.card_id
        with self.lock:
            if card_id in self._cards and not replace:
                raise ValueError(f"卡片已注册: {card_id}")
            self._cards[card_id] = card
        return card

    def unregister(self, card_id: str) -> Card | None:
        with self.lock:
            return self._cards.pop(str(card_id), None)

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
