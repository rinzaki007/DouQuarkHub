"""Quark online-playback card.

Uses the credential already saved by the Quark storage card; it never stores a second Cookie.
"""
from __future__ import annotations

import re
from typing import Any

from moviesync.cards import CardManifest, PlaybackProviderCard
from moviesync.clients.quark import QuarkClient

_FID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class QuarkPlaybackCard(PlaybackProviderCard):
    manifest = CardManifest(
        id="quark_playback",
        name="夸克在线播放",
        type="playback_provider",
        description="浏览本人夸克网盘目录并在 MovieSync 页面内播放视频",
        capabilities=("playback.list_files", "playback.resolve", "playback.health_check"),
    )

    def __init__(self, config_store):
        self.config_store = config_store

    def _quark_config(self) -> dict[str, Any]:
        getter = getattr(self.config_store, "get_card_config", None)
        if not callable(getter):
            return {}
        value = getter("quark")
        return value if isinstance(value, dict) else {}

    def _client(self) -> QuarkClient:
        return QuarkClient(str(self._quark_config().get("cookie") or "").strip())

    def is_configured(self, config: dict[str, Any]) -> bool:
        return bool(str(self._quark_config().get("cookie") or "").strip())

    def check(self, config: dict | None = None) -> dict[str, Any]:
        if not self.is_configured({}):
            return {"status": "unconfigured", "message": "请先在夸克存储卡片中配置 Cookie"}
        healthy = self._client().check_cookie_valid()
        return {
            "status": "healthy" if healthy else "unavailable",
            "message": "夸克 Cookie 有效" if healthy else "夸克 Cookie 无效或已过期",
        }

    def _persist_refreshed_cookie(self, client: QuarkClient) -> None:
        """Persist Quark's rotated session cookies without touching other card settings."""
        cookie = client.get_cookie()
        getter = getattr(self.config_store, "get_card_config", None)
        saver = getattr(self.config_store, "save_card_config", None)
        if not cookie or not callable(getter) or not callable(saver):
            return
        try:
            current = getter("quark")
            current_cookie = str(current.get("cookie") or "") if isinstance(current, dict) else ""
            if cookie != current_cookie:
                saver("quark", {"cookie": cookie})
        except Exception:
            # Playback must remain usable even if an optional persistence API is unavailable.
            return

    def list_files(self, parent_fid: str = "0") -> list[dict[str, Any]]:
        fid = str(parent_fid or "0").strip()
        if not _FID_RE.fullmatch(fid):
            raise ValueError("目录 FID 格式无效")
        client = self._client()
        try:
            return client.list_drive_files(fid)
        finally:
            self._persist_refreshed_cookie(client)

    def resolve_playback(self, fid: str) -> dict[str, Any]:
        file_id = str(fid or "").strip()
        if not _FID_RE.fullmatch(file_id):
            raise ValueError("文件 FID 格式无效")
        client = self._client()
        try:
            info = client.get_playback_info(file_id)
        finally:
            self._persist_refreshed_cookie(client)
        return {
            "fid": file_id,
            "file_name": str(info.get("file_name") or ""),
            "url": str(info["url"]),
            "resolution": str(info.get("resolution") or ""),
            "format": str(info.get("format") or ""),
            "mime_type": str(info.get("mime_type") or "video/mp4"),
            "size": info.get("size") or 0,
        }


def create_card(context):
    return QuarkPlaybackCard(context["config_store"])
