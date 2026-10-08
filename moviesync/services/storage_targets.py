"""统一存储目标卡片管理。

核心业务只通过 StorageTargetManager 使用存储能力，不直接依赖 Quark、115、
百度网盘等具体平台。具体平台差异由 StorageTargetCard 自己处理。
"""

from __future__ import annotations

from typing import Any

from ..cards import CardRegistry, StorageTargetCard


class StorageTargetManager:
    """管理已加载的存储目标卡片。"""

    def __init__(self, registry: CardRegistry, config_store, logger):
        self.registry = registry
        self.config_store = config_store
        self.logger = logger

    def _enabled_cards(self) -> list[StorageTargetCard]:
        cards = []
        config = self.config_store.load()
        card_configs = config.get("cards") if isinstance(config, dict) else {}
        for card in self.registry.find_by_type("storage_target"):
            if not isinstance(card, StorageTargetCard):
                continue
            saved = card_configs.get(card.card_id) if isinstance(card_configs, dict) else {}
            if not isinstance(saved, dict) or saved.get("enabled", True):
                cards.append(card)
        return cards

    def get(self, target_id: str | None = None) -> StorageTargetCard | None:
        if target_id:
            card = self.registry.get(str(target_id))
            if not isinstance(card, StorageTargetCard):
                return None
            config = self.config_store.load()
            card_configs = config.get("cards") if isinstance(config, dict) else {}
            saved = card_configs.get(card.card_id) if isinstance(card_configs, dict) else {}
            if isinstance(saved, dict) and not saved.get("enabled", True):
                return None
            return card
        default_id = self.config_store.get_default_storage_target_id()
        if default_id:
            card = self.registry.get(default_id)
            if isinstance(card, StorageTargetCard):
                config = self.config_store.load()
                card_configs = config.get("cards") if isinstance(config, dict) else {}
                saved = card_configs.get(card.card_id) if isinstance(card_configs, dict) else {}
                if not isinstance(saved, dict) or saved.get("enabled", True):
                    return card
        cards = self._enabled_cards()
        return cards[0] if cards else None

    def list_targets(self) -> list[dict[str, Any]]:
        config = self.config_store.load()
        card_configs = config.get("cards") if isinstance(config, dict) else {}
        results = []
        for card in self.registry.find_by_type("storage_target"):
            saved = card_configs.get(card.card_id) if isinstance(card_configs, dict) else {}
            enabled = not isinstance(saved, dict) or bool(saved.get("enabled", True))
            results.append({
                **card.manifest.to_dict(),
                "enabled": enabled,
            })
        return results

    def resolve_resource(
        self,
        resource: object,
        target_id: str | None = None,
    ) -> dict[str, Any]:
        resource_dict = dict(resource) if isinstance(resource, dict) else {}
        selected_id = (
            target_id
            or resource_dict.get("storage_target_id")
            or resource_dict.get("target_id")
        )
        card = self.get(str(selected_id) if selected_id else None)
        if not card:
            return {
                "target_id": str(selected_id or ""),
                "files": [],
                "token": None,
                "error": "未找到可用的存储目标卡片",
            }
        result = card.resolve_resource(resource_dict)
        result["target_id"] = card.card_id
        return result

    def list_files(
        self,
        resource: object,
        target_id: str | None = None,
    ) -> list[dict[str, Any]]:
        card = self.get(target_id)
        if not card:
            return []
        return card.list_files(resource)

    def create_folder(
        self,
        name: str,
        parent_id: str = "0",
        target_id: str | None = None,
    ) -> str:
        card = self.get(target_id)
        if not card:
            raise RuntimeError("未找到可用的存储目标卡片")
        return card.create_folder(name, parent_id)

    def transfer(
        self,
        resource: object,
        files: list[dict[str, Any]],
        target_id: str = "0",
        storage_target_id: str | None = None,
        token: str | None = None,
    ) -> tuple[bool, str]:
        card = self.get(storage_target_id)
        if not card:
            return False, "未找到可用的存储目标卡片"
        payload = dict(resource) if isinstance(resource, dict) else {}
        if token:
            payload["stoken"] = token
        return card.transfer(payload, files, target_id)
