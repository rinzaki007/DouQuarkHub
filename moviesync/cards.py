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
