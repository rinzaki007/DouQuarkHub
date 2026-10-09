"""Demonstration MovieSync storage-target plugin.

This card intentionally performs no real cloud operations. It demonstrates the
external package and entry-point contract without storing credentials or
transferring user files.
"""

from __future__ import annotations

from typing import Any

from moviesync.cards import CardManifest, StorageTargetCard


class ExampleStorageCard(StorageTargetCard):
    manifest = CardManifest(
        id="example-storage",
        name="示例存储（仅演示）",
        version="0.1.0",
        type="storage_target",
        description="用于验证第三方安装式插件接入；不会访问网盘或转存真实文件。",
        capabilities=(
            "storage.check",
            "storage.resolve_resource",
            "storage.list_files",
            "storage.create_folder",
            "storage.transfer",
        ),
        config_fields=(
            {
                "key": "display_name",
                "label": "显示名称",
                "type": "string",
                "required": True,
                "default": "我的示例存储",
            },
        ),
    )

    def check(self, config: dict[str, Any]) -> dict[str, Any]:
        display_name = str(config.get("display_name") or "").strip()
        if not display_name:
            return {"status": "unconfigured", "message": "请填写显示名称"}
        return {
            "status": "healthy",
            "message": f"{display_name} 插件已加载（演示模式，不连接外部服务）",
        }

    def resolve_resource(self, resource: object) -> dict[str, Any]:
        return {
            "files": [],
            "token": None,
            "error": "这是示例插件，不支持解析真实分享链接",
        }

    def list_files(self, resource: object) -> list[dict[str, Any]]:
        return []

    def destination_options(self) -> list[dict[str, Any]]:
        return [{"id": "demo-root", "name": "示例目录（虚拟）", "is_default": True}]

    def create_folder(self, name: str, parent_id: str = "demo-root") -> str:
        raise RuntimeError("这是示例插件，不会创建真实目录")

    def transfer(
        self,
        resource: object,
        files: list[dict[str, Any]],
        target_id: str = "demo-root",
    ) -> tuple[bool, str]:
        return False, "这是示例插件，不会执行真实转存"


def create_card(context: dict[str, Any]) -> StorageTargetCard:
    """Entry-point factory called by MovieSync at application startup."""
    # Keep the factory signature aligned with the contract. This demo does not
    # need shared services, but real plugins can use context["config_store"]
    # and context["logger"] when needed.
    _ = context
    return ExampleStorageCard()
