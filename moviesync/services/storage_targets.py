"""统一存储目标卡片管理。

核心业务只通过 StorageTargetManager 使用存储能力，不直接依赖 Quark、115、
百度网盘等具体平台。具体平台差异由 StorageTargetCard 自己处理。
"""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any

from ..cards import CardRegistry, StorageTargetCard


class StorageTargetManager:
    """管理已加载的存储目标卡片。"""

    def __init__(self, registry: CardRegistry, config_store, logger):
        self.registry = registry
        self.config_store = config_store
        self.logger = logger

    def load_plugins(self, context: dict[str, Any] | None = None) -> list[str]:
        """加载已安装可信 Python 包声明的存储卡片插件。

        插件通过 moviesync.storage_targets entry point 暴露工厂函数。
        工厂接收 context 字典并返回 StorageTargetCard 实例。这里仅发现
        当前 Python 环境中已安装的包；不接受后台上传或执行任意代码。
        """
        loaded: list[str] = []
        plugin_context = dict(context or {})
        try:
            candidates = entry_points(group="moviesync.storage_targets")
        except Exception:
            self.logger.exception("读取存储卡片插件入口失败")
            return loaded

        for entry_point in candidates:
            try:
                factory = entry_point.load()
                if not callable(factory):
                    raise TypeError("插件入口必须指向可调用的工厂函数")
                card = factory(plugin_context)
                if not isinstance(card, StorageTargetCard):
                    raise TypeError("存储卡片插件工厂必须返回 StorageTargetCard 实例")
                if card.card_type != "storage_target":
                    raise ValueError("卡片类型必须是 storage_target")
                registered = self.registry.register(card)
                loaded.append(registered.card_id)
                self.logger.info("已加载存储卡片插件: %s", registered.card_id)
            except Exception:
                self.logger.exception("存储卡片插件 %s 加载失败", entry_point.name)
        return loaded

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

    def _unavailable_message(self, target_id: str | None = None) -> str:
        if target_id:
            card = self.registry.get(str(target_id))
            if isinstance(card, StorageTargetCard):
                config = self.config_store.load()
                card_configs = config.get("cards") if isinstance(config, dict) else {}
                saved = card_configs.get(card.card_id) if isinstance(card_configs, dict) else {}
                if isinstance(saved, dict) and not saved.get("enabled", True):
                    return f"存储目标卡片「{card.manifest.name}」已停用，请重新启用后重试"
        return "未找到可用的存储目标卡片"

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
        getter = getattr(self.config_store, "get_default_storage_target_id", None)
        default_id = getter() if callable(getter) else ""
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

    def destination_options(self, target_id: str | None = None) -> list[dict[str, Any]]:
        card = self.get(target_id)
        if not card:
            return []
        return card.destination_options()

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
                "error": self._unavailable_message(str(selected_id) if selected_id else None),
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
            raise RuntimeError(self._unavailable_message(target_id))
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
            return False, self._unavailable_message(storage_target_id)
        payload = dict(resource) if isinstance(resource, dict) else {}
        if token:
            payload["stoken"] = token
        return card.transfer(payload, files, target_id)
