"""资源来源抽象层。

用途：将资源发现入口与 MovieSync 核心业务解耦。当前内置 Telegram，
以后可在不改搜索、任务中心和转存逻辑的情况下增加其他合法资源源。
"""

from __future__ import annotations

import re
import threading
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import entry_points
from typing import Any

from ..cards import Card, CardManifest, CardRegistry, ResourceSourceCard
from ..clients.telegram import TelegramClient
from ..config_store import ConfigStore, ConfigValidationError
from .filename_rules import parse_tv_episode


class ResourceSource(ResourceSourceCard):
    """资源发现卡片的兼容基类。

    旧代码仍可继续通过 ResourceSource 使用，新的实现统一遵循 Card 接口。
    """

    source_id = "unknown"
    name = "未命名资源源"
    source_type = "custom"
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


class TelegramResourceSource(ResourceSource):
    source_id = "telegram"
    name = "Telegram"
    source_type = "telegram"
    manifest = CardManifest(
        id="telegram",
        name="Telegram",
        version="1.0.0",
        type="resource_source",
        description="Telegram 公开频道资源发现卡片",
        capabilities=("resource.search", "resource.health_check"),
        config_fields=(
            {
                "key": "channels",
                "label": "资源频道",
                "type": "json",
                "default": [],
                "description": "JSON 数组，每项包含频道 id，可选 name。",
            },
            {
                "key": "magic_regex",
                "label": "文件名识别增强",
                "type": "json",
                "default": {},
                "description": "JSON 对象，可配置 pattern 与 replace。",
            },
        ),
    )

    def __init__(self, client: TelegramClient, config_store=None):
        self.client = client
        self.config_store = config_store

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """验证 Telegram 频道与文件名正则，统一通用配置和旧接口规则。"""
        normalized = super().validate_config(config)
        normalized["channels"] = ConfigStore._normalize_channels(normalized.get("channels", []))
        magic_regex = normalized.get("magic_regex", {})
        if magic_regex is None:
            magic_regex = {}
        if not isinstance(magic_regex, dict):
            raise ConfigValidationError("magic_regex 必须是 JSON 对象")
        pattern = str(magic_regex.get("pattern") or "").strip()
        replacement = str(magic_regex.get("replace") or "")
        if len(pattern) > 1000 or len(replacement) > 200:
            raise ConfigValidationError("文件名正则或替换规则过长")
        try:
            if pattern:
                re.compile(pattern)
        except re.error as exc:
            raise ConfigValidationError(f"文件名正则无效：{exc}") from exc
        normalized["magic_regex"] = {"pattern": pattern, "replace": replacement}
        return normalized

    def search(self, movie: object, config: dict) -> list[dict[str, Any]]:
        channels = config.get("channels") or []
        title = str(
            movie.get("title", movie.get("name", ""))
            if isinstance(movie, dict)
            else movie
        ).strip()
        if not title or not channels:
            return []

        results: list[dict[str, Any]] = []
        with ThreadPoolExecutor(
            max_workers=min(8, max(1, len(channels)))
        ) as executor:
            futures = [
                executor.submit(self.client.search_channel, channel, title)
                for channel in channels
            ]
            for future in futures:
                try:
                    for item in future.result():
                        results.append(
                            {
                                **item,
                                "source_id": self.source_id,
                                "source_name": self.name,
                                "storage_target_id": item.get("storage_target_id", ""),
                            }
                        )
                except Exception:
                    continue
        return results

    def search_channel(self, channel: object, title: str, config: dict) -> list[dict[str, Any]]:
        # 自动追剧要扫描频道最近的消息，而不是只依赖 Telegram 的标题查询结果；
        # 后续仍由客户端做标题匹配并受页数上限保护。
        return self.client.search_channel(channel, title, scan_all=True)


    def check(self, config: dict) -> dict[str, Any]:
        channels = config.get("channels") or []
        if not channels:
            return {
                "status": "idle",
                "message": "未配置 Telegram 频道",
                "total": 0,
                "valid_count": 0,
            }

        with ThreadPoolExecutor(
            max_workers=min(8, max(1, len(channels)))
        ) as executor:
            results = list(
                executor.map(
                    self.client.check_channel_detail,
                    channels,
                )
            )

        channel_results = []
        for channel, detail in zip(channels, results, strict=True):
            channel_id = str(
                channel.get("id", "")
                if isinstance(channel, dict)
                else channel
            ).strip().lstrip("@")
            channel_name = str(
                channel.get("name", channel_id)
                if isinstance(channel, dict)
                else channel_id
            ).strip() or channel_id
            channel_results.append(
                {
                    "id": channel_id,
                    "name": channel_name,
                    **detail,
                }
            )

        valid_count = sum(
            item.get("status") == "healthy"
            for item in channel_results
        )
        total = len(channels)
        if valid_count == total:
            status = "healthy"
            message = "所有已配置频道正常"
        elif valid_count:
            status = "degraded"
            message = f"{total - valid_count} 个频道不可用"
        else:
            status = "unavailable"
            message = "所有已配置频道均不可用"

        return {
            "status": status,
            "message": message,
            "total": total,
            "valid_count": valid_count,
            "channels": channel_results,
        }


class PanSouResourceSource(ResourceSource):
    """PanSou Web 搜索适配器。

    当前只输出可由内置 Quark 存储卡解析的夸克分享链接；
    其他网盘类型不会被错误地交给 Quark。
    """

    source_id = "pansou"
    name = "PanSou"
    source_type = "pansou"
    manifest = CardManifest(
        id="pansou",
        name="PanSou",
        version="1.0.0",
        type="resource_source",
        description="使用 MovieSync 内置 PanSou 搜索夸克分享资源，也可连接外部 PanSou 服务",
        capabilities=("resource.search", "resource.health_check"),
        config_fields=(
            {
                "key": "base_url",
                "label": "PanSou 地址（默认内置）",
                "type": "string",
                "format": "url",
                "required": False,
                "default": "http://127.0.0.1:8888",
                "max_length": 500,
                "placeholder": "http://127.0.0.1:8888",
                "description": "默认使用 MovieSync 内置 PanSou，无需单独部署。仅在接入外部 PanSou 时修改此地址。",
            },
            {
                "key": "username",
                "label": "PanSou 用户名",
                "type": "string",
                "required": False,
                "max_length": 128,
                "description": "仅在 PanSou 启用了认证时填写。",
            },
            {
                "key": "password",
                "label": "PanSou 密码",
                "type": "password",
                "secret": True,
                "required": False,
                "max_length": 256,
                "description": "仅在 PanSou 启用了认证时填写；不会回显到页面。",
            },
            {
                "key": "timeout",
                "label": "请求超时（秒）",
                "type": "number",
                "default": 45,
                "description": "PanSou 搜索可能较慢，建议 30–60 秒。",
            },
        ),
    )

    def __init__(self, http_client=None):
        from ..clients.http import HttpClient

        self.http = http_client or HttpClient()
        self._token = ""
        self._token_expires_at = 0.0
        self._auth_lock = threading.RLock()

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        from urllib.parse import urlparse

        normalized = super().validate_config(config)
        base_url = str(normalized.get("base_url") or "").strip().rstrip("/")
        if base_url:
            parsed = urlparse(base_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ConfigValidationError("PanSou 地址必须是有效的 HTTP 或 HTTPS URL")
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ConfigValidationError("PanSou 地址不能包含账号密码、查询参数或片段")
        normalized["base_url"] = base_url
        normalized["username"] = str(normalized.get("username") or "").strip()
        normalized["password"] = str(normalized.get("password") or "")
        timeout = normalized.get("timeout", 45)
        if isinstance(timeout, bool):
            raise ConfigValidationError("PanSou 请求超时必须是 5–120 秒之间的数字")
        try:
            timeout = int(timeout)
        except (TypeError, ValueError) as exc:
            raise ConfigValidationError("PanSou 请求超时必须是 5–120 秒之间的数字") from exc
        if not 5 <= timeout <= 120:
            raise ConfigValidationError("PanSou 请求超时必须是 5–120 秒之间的数字")
        normalized["timeout"] = timeout
        return normalized

    @staticmethod
    def _base_url(self, config: dict[str, Any]) -> str:
        import os

        return str(
            config.get("base_url") or os.environ.get("MOVIESYNC_PANSOU_URL") or ""
        ).strip().rstrip("/")

    @staticmethod
    def _payload(data: dict[str, Any]) -> dict[str, Any]:
        wrapped = data.get("data")
        return wrapped if isinstance(wrapped, dict) else data

    def _login(self, base_url: str, config: dict[str, Any], timeout: int) -> str:
        username = str(config.get("username") or "").strip()
        password = str(config.get("password") or "")
        if not username or not password:
            raise RuntimeError("PanSou 已启用认证，请在 PanSou 卡片中填写用户名和密码")
        response, data = self.http.request_json(
            "POST",
            f"{base_url}/api/auth/login",
            timeout=timeout,
            retries=0,
            json={"username": username, "password": password},
        )
        if response.status_code != 200:
            raise RuntimeError("PanSou 登录失败，请检查用户名、密码及服务状态")
        payload = self._payload(data)
        token = str(payload.get("token") or "").strip()
        if not token:
            raise RuntimeError("PanSou 登录响应中没有 Token")
        expires_at = payload.get("expires_at")
        try:
            expiry = float(expires_at) if expires_at else 0.0
        except (TypeError, ValueError):
            expiry = 0.0
        import time

        with self._auth_lock:
            self._token = token
            self._token_expires_at = expiry or (time.time() + 3600)
        return token

    def _request(
        self,
        method: str,
        url: str,
        config: dict[str, Any],
        *,
        timeout: int,
        params: dict[str, Any] | None = None,
    ) -> tuple[Any, dict[str, Any]]:
        import time

        base_url = self._base_url(config)
        headers: dict[str, str] = {}
        with self._auth_lock:
            token = self._token
            expires_at = self._token_expires_at
        if token and expires_at > time.time() + 30:
            headers["Authorization"] = f"Bearer {token}"

        response, data = self.http.request_json(
            method, url, timeout=timeout, retries=0, params=params, headers=headers
        )
        if response.status_code == 401:
            token = self._login(base_url, config, timeout)
            response, data = self.http.request_json(
                method,
                url,
                timeout=timeout,
                retries=0,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise RuntimeError(f"PanSou 请求失败（HTTP {response.status_code}）")
        return response, self._payload(data)

    @staticmethod
    def _quark_share_id(url: object) -> str:
        from urllib.parse import urlparse

        value = str(url or "").strip()
        try:
            parsed = urlparse(value)
        except ValueError:
            return ""
        host = (parsed.hostname or "").lower()
        if not (host == "quark.cn" or host.endswith(".quark.cn")):
            return ""
        match = re.match(r"^/s/([A-Za-z0-9_-]{1,128})(?:/|$)", parsed.path)
        return match.group(1) if match else ""

    def _normalize_link(
        self,
        item: dict[str, Any],
        *,
        title: str = "",
        channel: str = "",
    ) -> dict[str, Any] | None:
        link_url = str(item.get("url") or "").strip()
        share_id = self._quark_share_id(link_url)
        if not share_id:
            return None
        return {
            "pwd_id": share_id,
            "url": link_url,
            "password": str(item.get("password") or item.get("passcode") or "").strip(),
            "storage_target_id": "quark",
            "title": title[:500],
            "channel": channel[:200],
        }

    def search(self, movie: object, config: dict) -> list[dict[str, Any]]:
        title = str(
            movie.get("title", movie.get("name", ""))
            if isinstance(movie, dict)
            else movie
        ).strip()
        base_url = self._base_url(config)
        if not title or not base_url:
            return []
        try:
            timeout = int(config.get("timeout", 45))
        except (TypeError, ValueError):
            timeout = 45
        _, payload = self._request(
            "GET",
            f"{base_url}/api/search",
            config,
            timeout=timeout,
            params={
                "kw": title,
                "res": "all",
                "src": "all",
                "cloud_types": "quark",
            },
        )
        results: list[dict[str, Any]] = []
        seen: set[str] = set()

        raw_results = payload.get("results")
        if isinstance(raw_results, list):
            for result in raw_results:
                if not isinstance(result, dict):
                    continue
                links = result.get("links")
                if not isinstance(links, list):
                    continue
                result_title = str(result.get("title") or result.get("content") or title)
                channel = str(result.get("channel") or result.get("source") or "")
                for link in links:
                    if not isinstance(link, dict):
                        continue
                    link_type = str(link.get("type") or "").lower()
                    if link_type and "quark" not in link_type and "夸克" not in link_type:
                        continue
                    normalized = self._normalize_link(
                        link, title=result_title, channel=channel
                    )
                    if normalized and normalized["pwd_id"] not in seen:
                        seen.add(normalized["pwd_id"])
                        results.append(normalized)

        # 兼容只返回按网盘类型聚合结果的 PanSou 部署版本。
        merged = payload.get("merged_by_type")
        if isinstance(merged, dict):
            for cloud_type, items in merged.items():
                if "quark" not in str(cloud_type).lower() and "夸克" not in str(cloud_type):
                    continue
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    normalized = self._normalize_link(
                        item,
                        title=str(item.get("note") or title),
                        channel=str(item.get("source") or ""),
                    )
                    if normalized and normalized["pwd_id"] not in seen:
                        seen.add(normalized["pwd_id"])
                        results.append(normalized)
        return results

    def check(self, config: dict) -> dict[str, Any]:
        base_url = self._base_url(config)
        if not base_url:
            return {
                "status": "unconfigured",
                "message": "尚未配置 PanSou 地址",
                "total": 0,
                "valid_count": 0,
            }
        try:
            timeout = int(config.get("timeout", 45))
            response, payload = self._request(
                "GET",
                f"{base_url}/api/health",
                config,
                timeout=min(timeout, 15),
            )
            if response.status_code != 200:
                raise RuntimeError("PanSou 健康检查失败")
            enabled_plugins = payload.get("plugins_enabled")
            return {
                "status": "healthy",
                "message": (
                    f"PanSou 连接正常，已启用 {payload.get('plugin_count', 0)} 个搜索插件"
                    if enabled_plugins is not False
                    else "PanSou 可连接，但当前没有启用搜索插件"
                ),
                "total": int(payload.get("plugin_count") or 0),
                "valid_count": int(payload.get("plugin_count") or 0),
            }
        except Exception:
            return {
                "status": "unavailable",
                "message": "PanSou 连接失败，请检查地址、认证配置和服务日志",
                "total": 0,
                "valid_count": 0,
            }


class ResourceSourceManager:
    """管理已注册资源源，并提供统一搜索/健康检查入口。"""

    def __init__(
        self,
        telegram: TelegramClient,
        config_store,
        logger,
        registry: CardRegistry | None = None,
        resource_cards: Iterable[ResourceSourceCard] | None = None,
    ):
        self.logger = logger
        self.config_store = config_store
        self.registry = registry or CardRegistry()

        # 默认资源源仅在未注册时加载；允许应用装配层预先注册卡片。
        if self.registry.get("telegram") is None:
            self.registry.register(TelegramResourceSource(telegram))
        for card in resource_cards or ():
            self.register(card)

    @property
    def sources(self) -> dict[str, ResourceSourceCard]:
        """返回注册表中的当前资源源快照，避免保留已注销卡片的旧引用。"""
        return {
            card.card_id: card
            for card in self.registry.find_by_type("resource_source")
            if isinstance(card, ResourceSourceCard)
        }

    def register(self, card: ResourceSourceCard, *, replace: bool = False) -> ResourceSourceCard:
        """注册资源来源卡片。第三方实现应由应用启动时的可信代码显式装配。"""
        if not isinstance(card, ResourceSourceCard):
            raise TypeError("资源来源卡片必须继承 ResourceSourceCard")
        if card.card_type != "resource_source":
            raise ValueError("卡片类型必须是 resource_source")
        return self.registry.register(card, replace=replace)

    @staticmethod
    def _source_name(source: ResourceSourceCard) -> str:
        return str(getattr(source, "name", "") or source.manifest.name or source.card_id)

    @staticmethod
    def _source_type(source: ResourceSourceCard) -> str:
        return str(getattr(source, "source_type", "") or source.card_type)


    def load_plugins(self, context: dict[str, Any] | None = None) -> list[str]:
        """加载已安装 Python 包声明的资源卡片插件。

        插件通过 moviesync.resource_sources entry point 暴露一个工厂函数，
        工厂接收 context 字典并返回 ResourceSourceCard。仅加载环境中已安装
        的可信 Python 包；不接受从 Web 上传或执行任意代码。
        """
        loaded: list[str] = []
        plugin_context = dict(context or {})
        try:
            candidates = entry_points(group="moviesync.resource_sources")
        except Exception as exc:
            self.logger.exception("读取资源卡片插件入口失败: %s", exc)
            return loaded

        for entry_point in candidates:
            card = None
            try:
                factory = entry_point.load()
                if not callable(factory):
                    raise TypeError("插件入口必须指向可调用的工厂函数")
                card = factory(plugin_context)
                self.register(card)
                loaded.append(card.card_id)
                self.logger.info("已加载资源卡片插件: %s", card.card_id)
            except Exception as exc:
                self._close_unregistered_plugin_card(card, entry_point.name)
                self.logger.exception("资源卡片插件 %s 加载失败: %s", entry_point.name, exc)
        return loaded


    def _close_unregistered_plugin_card(self, card: object, plugin_name: str) -> None:
        """工厂已创建但未成功注册的卡片也必须释放资源。"""
        if not isinstance(card, Card):
            return
        try:
            if self.registry.get(card.card_id) is card:
                return
            card.close()
        except Exception:
            self.logger.exception("清理未注册资源卡片插件 %s 失败", plugin_name)

    def get_cards(self) -> list[dict[str, Any]]:
        """仅返回已加载资源来源卡片的 Manifest。"""
        return [
            card.manifest.to_dict()
            for card in self.registry.find_by_type("resource_source")
            if isinstance(card, ResourceSourceCard)
        ]
    def _card_config(self, config: dict, source_id: str) -> dict[str, Any]:
        cards = config.get("cards") if isinstance(config, dict) else {}
        card = cards.get(source_id) if isinstance(cards, dict) else {}
        if not isinstance(card, dict):
            return {}
        card_config = card.get("config")
        return dict(card_config) if isinstance(card_config, dict) else {}

    def _enabled_sources(self, config: dict) -> list[ResourceSourceCard]:
        enabled = []
        cards = config.get("cards") if isinstance(config, dict) else {}
        for source_id, source in self.sources.items():
            card = cards.get(source_id) if isinstance(cards, dict) else {}
            if not isinstance(card, dict) or card.get("enabled", True):
                enabled.append(source)
        return enabled

    def search(self, movie: object, config: dict) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for source in self._enabled_sources(config):
            try:
                items = source.search(movie, self._card_config(config, source.card_id))
                if not isinstance(items, list):
                    raise TypeError("资源卡片 search 必须返回列表")
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    results.append({
                        **item,
                        # Resource identity is owned by the manager, not plugin output.
                        "source_id": source.card_id,
                        "source_name": self._source_name(source),
                    })
            except Exception as exc:
                self.logger.exception(
                    "资源源 %s 搜索异常: %s",
                    source.card_id,
                    exc,
                )
        return results

    def parse_tv_episode(self, source_id: str, file_name: str) -> tuple[int | None, int | None]:
        """通过对应资源卡片的配置解析集数，核心订阅逻辑不绑定具体正则。"""
        config = self.config_store.load()
        source = self.sources.get(str(source_id))
        card_config = self._card_config(config, source.card_id) if source else {}
        return parse_tv_episode(file_name, card_config.get("magic_regex"))

    def search_channel(self, source_id: str, channel: object, title: str) -> list[dict[str, Any]]:
        config = self.config_store.load()
        source = self.sources.get(str(source_id))
        if not source:
            return []
        cards = config.get("cards") if isinstance(config, dict) else {}
        card = cards.get(source.card_id) if isinstance(cards, dict) else {}
        if isinstance(card, dict) and not card.get("enabled", True):
            return []
        try:
            return source.search_channel(
                channel,
                str(title or "").strip(),
                self._card_config(config, source.card_id),
            )
        except Exception as exc:
            self.logger.exception("资源源 %s 频道检索异常: %s", source.card_id, exc)
            return []


    def check_all(self) -> list[dict[str, Any]]:
        config = self.config_store.load()
        cards = config.get("cards") if isinstance(config, dict) else {}
        results = []

        for source_id, source in self.sources.items():
            card = cards.get(source_id) if isinstance(cards, dict) else {}
            enabled = not isinstance(card, dict) or bool(card.get("enabled", True))
            if not enabled:
                result = {
                    "id": source_id,
                    "name": self._source_name(source),
                    "type": self._source_type(source),
                    "enabled": False,
                    "status": "disabled",
                    "message": "资源源已停用",
                    "total": 0,
                    "valid_count": 0,
                }
            else:
                try:
                    check = source.check(self._card_config(config, source_id))
                    result = {
                        **check,
                        "id": source_id,
                        "name": self._source_name(source),
                        "type": self._source_type(source),
                        "enabled": True,
                    }
                except Exception:
                    self.logger.exception(
                        "资源源 %s 健康检查异常",
                        source_id,
                    )
                    result = {
                        "id": source_id,
                        "name": self._source_name(source),
                        "type": self._source_type(source),
                        "enabled": True,
                        "status": "unavailable",
                        "message": "资源来源连接检查失败，请查看服务日志",
                        "total": 0,
                        "valid_count": 0,
                    }

            results.append(result)
            update_health = getattr(self.config_store, "update_resource_source_health", None)
            if callable(update_health):
                try:
                    update_health(
                        source_id,
                        result["status"],
                        result.get("message", ""),
                        result.get("channels"),
                    )
                except Exception:
                    # Persisting one card's health must not prevent checking the
                    # remaining sources or returning the already-computed results.
                    self.logger.exception("保存资源源 %s 健康状态失败", source_id)

        return results

    def get_status(self) -> list[dict[str, Any]]:
        return self.config_store.get_resource_sources()
