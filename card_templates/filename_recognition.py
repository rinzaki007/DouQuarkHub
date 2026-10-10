"""Global filename-recognition settings shared by all resource sources."""
from __future__ import annotations

import re
from typing import Any

from moviesync.cards import CardManifest, FilenameProcessorCard
from moviesync.errors import ConfigValidationError
from moviesync.regex_safety import has_nested_unbounded_quantifier
from moviesync.services.filename_rules import DEFAULT_TV_MAGIC_REGEX, parse_tv_episode


class FilenameRecognitionCard(FilenameProcessorCard):
    """Configure the global filename episode-recognition rules."""

    manifest = CardManifest(
        id="filename_recognition",
        name="文件名识别",
        version="1.0.0",
        type="filename_processor",
        description="统一识别不同资源来源中的季集信息和特殊文件命名。",
        capabilities=("filename.parse", "filename.normalize"),
        config_fields=(
            {
                "key": "magic_regex",
                "label": "特殊命名规则",
                "type": "json",
                "editor": "object_fields",
                "item_fields": (
                    {"key": "pattern", "label": "匹配规则", "placeholder": "例如：自定义文件名匹配表达式"},
                    {"key": "replace", "label": "替换规则", "placeholder": "例如：统一后的剧名和集数格式"},
                ),
                "default": DEFAULT_TV_MAGIC_REGEX,
                "description": (
                    "这里的规则对所有资源来源生效，不只限于 Telegram。"
                    "常见 S01E02、第 2 集等格式会优先使用内置识别；"
                    "只有内置规则无法识别时才会尝试此规则。"
                ),
            },
        ),
    )

    def parse_episode(
        self, file_name: str, config: dict[str, Any]
    ) -> tuple[int | None, int | None]:
        """先使用通用内置格式，再应用本卡片配置的特殊命名规则。"""
        builtin = parse_tv_episode(file_name, {"pattern": "", "replace": ""})
        if builtin[1] is not None:
            return builtin
        magic = config.get("magic_regex") if isinstance(config, dict) else None
        if not isinstance(magic, dict) or not str(magic.get("pattern") or "").strip():
            return None, None
        return parse_tv_episode(file_name, magic)

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        normalized = super().validate_config(config)
        magic = normalized.get("magic_regex", DEFAULT_TV_MAGIC_REGEX)
        if magic is None:
            magic = DEFAULT_TV_MAGIC_REGEX
        if not isinstance(magic, dict):
            raise ConfigValidationError("特殊命名规则必须是对象")
        pattern = str(magic.get("pattern") or "").strip()
        replacement = str(magic.get("replace") or "")
        if len(pattern) > 1000 or len(replacement) > 200:
            raise ConfigValidationError("文件名匹配规则或替换规则过长")
        if has_nested_unbounded_quantifier(pattern):
            raise ConfigValidationError("文件名匹配规则包含不安全的嵌套重复")
        try:
            if pattern:
                re.compile(pattern)
        except re.error as exc:
            raise ConfigValidationError(f"文件名匹配规则无效：{exc}") from exc
        normalized["magic_regex"] = {"pattern": pattern, "replace": replacement}
        return normalized


def create_card(context):
    return FilenameRecognitionCard()
