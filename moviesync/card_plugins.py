"""Load trusted single-file card plugins from the persistent data directory.

Only administrator-provided Python files are accepted. A plugin file is executable
code, not a sandboxed data format; the web UI must warn users to install trusted code.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from threading import RLock
from typing import Any

from .cards import (
    Card,
    CardRegistry,
    MetadataProviderCard,
    NotificationCard,
    ResourceSourceCard,
    StorageTargetCard,
)

_PLUGIN_FILE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}\.py$")
_MAX_PLUGIN_BYTES = 256 * 1024


class CardFilePluginManager:
    """Manage one trusted card factory per Python file under the data directory."""

    def __init__(self, plugin_dir: Path, registry: CardRegistry, logger):
        self.plugin_dir = Path(plugin_dir).resolve()
        self.registry = registry
        self.logger = logger
        self.plugin_dir.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._loaded: dict[str, tuple[str, str]] = {}
        self._errors: dict[str, str] = {}
        self._context: dict[str, Any] = {}

    @staticmethod
    def validate_filename(filename: str) -> str:
        name = str(filename or "").strip()
        if not _PLUGIN_FILE_RE.fullmatch(name):
            raise ValueError("卡片文件名仅允许小写字母、数字、连字符和下划线，且必须以 .py 结尾")
        return name

    def list_plugins(self) -> list[dict[str, Any]]:
        with self._lock:
            items = []
            for path in sorted(self.plugin_dir.glob("*.py")):
                try:
                    filename = self.validate_filename(path.name)
                except ValueError:
                    continue
                loaded = self._loaded.get(filename)
                items.append({
                    "filename": filename,
                    "loaded": bool(loaded and self.registry.get(loaded[0]) is not None),
                    "card_id": loaded[0] if loaded else None,
                    "error": self._errors.get(filename, ""),
                    "size": path.stat().st_size,
                })
            return items

    def load_all(self, context: dict[str, Any] | None = None) -> list[str]:
        self._context = dict(context or {})
        loaded = []
        for item in self.list_plugins():
            try:
                card = self.load_file(item["filename"], self._context)
                loaded.append(card.card_id)
            except Exception as exc:
                self.logger.exception("单文件卡片 %s 加载失败", item["filename"])
                self._errors[item["filename"]] = str(exc)[:300]
        return loaded

    def load_file(self, filename: str, context: dict[str, Any] | None = None) -> Card:
        name = self.validate_filename(filename)
        path = (self.plugin_dir / name).resolve()
        if path.parent != self.plugin_dir or not path.is_file():
            raise ValueError("卡片文件不存在")
        with self._lock:
            current = self._loaded.get(name)
            if current and self.registry.get(current[0]) is not None:
                raise ValueError("该卡片文件已经加载")
            module_name = "moviesync_file_card_" + name[:-3].replace("-", "_")
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                raise ValueError("无法读取卡片 Python 文件")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            try:
                spec.loader.exec_module(module)
                factory = getattr(module, "create_card", None)
                if not callable(factory):
                    raise ValueError("卡片文件必须提供 create_card(context) 工厂函数")
                card = factory(dict(context if context is not None else self._context))
                self._validate_card(card, name)
                self.registry.register(card)
            except Exception:
                sys.modules.pop(module_name, None)
                raise
            self._loaded[name] = (card.card_id, module_name)
            self._errors.pop(name, None)
            self.logger.info("已加载单文件卡片 %s（%s）", card.card_id, name)
            return card

    @staticmethod
    def _validate_card(card: object, filename: str) -> None:
        if not isinstance(card, Card):
            raise TypeError("create_card(context) 必须返回 MovieSync Card 实例")
        expected_id = filename[:-3]
        if card.card_id != expected_id:
            raise ValueError(
                f"卡片 ID「{card.card_id}」必须与文件名「{expected_id}」一致"
            )
        expected_types = {
            "resource_source": ResourceSourceCard,
            "storage_target": StorageTargetCard,
            "metadata_provider": MetadataProviderCard,
            "notification": NotificationCard,
        }
        base = expected_types.get(card.card_type)
        if base is not None and not isinstance(card, base):
            raise TypeError(f"{card.card_type} 类型卡片必须继承 {base.__name__}")
        if card.card_type not in {
            "resource_source", "storage_target", "metadata_provider",
            "notification", "automation", "custom",
        }:
            raise ValueError("卡片声明了不支持的类型")

    def install(self, filename: str, content: bytes) -> Card:
        name = self.validate_filename(filename)
        if not isinstance(content, bytes) or not content:
            raise ValueError("卡片文件不能为空")
        if len(content) > _MAX_PLUGIN_BYTES:
            raise ValueError("卡片文件不能超过 256 KiB")
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("卡片文件必须使用 UTF-8 编码") from exc
        path = self.plugin_dir / name
        with self._lock:
            if path.exists():
                raise ValueError("同名卡片文件已存在")
            # Exclusive creation prevents overwriting a file during concurrent requests.
            with path.open("xb") as handle:
                handle.write(content)
            try:
                return self.load_file(name, self._context)
            except Exception:
                path.unlink(missing_ok=True)
                raise

    def uninstall(self, filename: str) -> dict[str, str]:
        name = self.validate_filename(filename)
        path = self.plugin_dir / name
        with self._lock:
            if not path.is_file():
                raise FileNotFoundError("卡片文件不存在")
            loaded = self._loaded.pop(name, None)
            card_id = loaded[0] if loaded else ""
            module_name = loaded[1] if loaded else ""
            if card_id:
                card = self.registry.get(card_id)
                if card is not None:
                    self.registry.unregister(card_id)
            if module_name:
                sys.modules.pop(module_name, None)
            path.unlink()
            self._errors.pop(name, None)
            self.logger.info("已卸载单文件卡片 %s（%s）", card_id or name, name)
            return {"filename": name, "card_id": card_id}
