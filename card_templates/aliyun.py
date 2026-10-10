"""Standalone Aliyun Drive storage-target card.

Uses the account refresh token for authenticated destination operations and the
public share APIs for resolving incoming Aliyun Drive links. Live transfer behavior
must be verified with a real account before treating this card as production-ready.
"""
from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import urlparse

from moviesync.cards import CardManifest, StorageTargetCard
from moviesync.clients.http import ApiError, HttpClient
from moviesync.errors import ConfigValidationError

_API = "https://api.aliyundrive.com"
_AUTH = "https://auth.aliyundrive.com"
_SHARE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Referer": "https://www.aliyundrive.com/",
    "Origin": "https://www.aliyundrive.com",
    "Content-Type": "application/json",
    "x-canary": "client=web,app=share,version=v2.3.1",
}
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_FOLDER_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _share_id(resource: object) -> str:
    if not isinstance(resource, dict):
        return ""
    raw = str(resource.get("resource_id") or resource.get("share_id") or "").strip()
    url = str(resource.get("url") or "").strip()
    if url:
        try:
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            is_alipan = host == "alipan.com" or host.endswith(".alipan.com")
            is_aliyundrive = host == "aliyundrive.com" or host.endswith(".aliyundrive.com")
            if is_alipan or is_aliyundrive:
                match = re.match(r"^/s/([A-Za-z0-9_-]{1,128})(?:/|$)", parsed.path)
                if match:
                    raw = match.group(1)
        except ValueError:
            return ""
    return raw if _ID_RE.fullmatch(raw) else ""


def _folder_id(value: object) -> str:
    result = str(value or "root").strip() or "root"
    if not _ID_RE.fullmatch(result) and result != "root":
        raise ConfigValidationError("阿里云盘目录 ID 格式无效")
    return result


class AliyunDriveStorageCard(StorageTargetCard):
    """阿里云盘存储卡片。凭据、分享解析和转存逻辑均独立于夸克。"""

    manifest = CardManifest(
        id="aliyun",
        name="阿里云盘",
        version="0.1.0",
        type="storage_target",
        description="解析阿里云盘分享、浏览目标目录并尝试原生转存；首次接入需实测认证与转存接口",
        capabilities=(
            "storage.check",
            "storage.accepts.aliyun_share",
            "storage.resolve_resource",
            "storage.list_files",
            "storage.create_folder",
            "storage.transfer",
        ),
        config_fields=(
            {
                "key": "refresh_token",
                "label": "阿里云盘 Refresh Token",
                "type": "password",
                "secret": True,
                "required": False,
                "max_length": 4096,
                "placeholder": "登录阿里云盘后获取；留空则保留已保存的值",
                "description": "优先使用可续期的 Refresh Token，而不是整段浏览器 Cookie。凭据不会回显。",
            },
            {
                "key": "default_drive_id",
                "label": "默认网盘 Drive ID（可选）",
                "type": "string",
                "required": False,
                "max_length": 128,
                "description": "通常自动读取账号默认网盘；仅在接口未返回时手动填写。",
            },
            {
                "key": "default_folder_id",
                "label": "默认保存目录 ID",
                "type": "string",
                "required": True,
                "default": "root",
                "max_length": 128,
                "description": "root 表示网盘根目录。",
            },
        ),
    )

    def __init__(self, config_store, http_client=None):
        self.config_store = config_store
        self.http = http_client or HttpClient()
        self._access_token = ""
        self._access_expires_at = 0.0
        self._refresh_token = ""
        self._drive_id = ""

    def _config(self) -> dict[str, Any]:
        getter = getattr(self.config_store, "get_card_config", None)
        if not callable(getter):
            return {}
        config = getter(self.card_id)
        return config if isinstance(config, dict) else {}

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        normalized = super().validate_config(config)
        normalized["refresh_token"] = str(normalized.get("refresh_token") or "").strip()
        normalized["default_drive_id"] = str(normalized.get("default_drive_id") or "").strip()
        normalized["default_folder_id"] = _folder_id(normalized.get("default_folder_id") or "root")
        return normalized

    def is_configured(self, config: dict[str, Any]) -> bool:
        return bool(str((config or {}).get("refresh_token") or "").strip())

    def _request(self, method: str, url: str, *, headers=None, json=None, params=None, timeout=12):
        try:
            response, payload = self.http.request_json(
                method,
                url,
                timeout=timeout,
                retries=0,
                headers=headers,
                json=json,
                params=params,
            )
        except ApiError as exc:
            raise RuntimeError("阿里云盘接口请求失败，请检查网络或登录状态") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("阿里云盘返回了无法识别的数据")
        if response.status_code < 200 or response.status_code >= 300:
            code = str(payload.get("code") or "")
            message = str(payload.get("message") or payload.get("msg") or "")
            if code in {"InvalidToken", "AccessTokenExpired", "401"} or response.status_code == 401:
                raise RuntimeError("阿里云盘登录凭据无效或已过期，请更新 Refresh Token")
            raise RuntimeError(f"阿里云盘请求失败（HTTP {response.status_code}，{code or message or '上游错误'}）")
        return payload

    def _ensure_login(self) -> tuple[str, str]:
        config = self._config()
        refresh_token = str(config.get("refresh_token") or "").strip()
        if not refresh_token:
            raise RuntimeError("尚未配置阿里云盘 Refresh Token")
        if self._access_token and self._access_expires_at > time.time() + 60 and self._refresh_token == refresh_token:
            return self._access_token, str(config.get("default_drive_id") or self._drive_id or "")
        payload = self._request(
            "POST",
            f"{_AUTH}/v2/account/token",
            headers=_SHARE_HEADERS,
            json={"grant_type": "refresh_token", "refresh_token": refresh_token},
        )
        access_token = str(payload.get("access_token") or "").strip()
        if not access_token:
            raise RuntimeError("阿里云盘未返回 Access Token，请检查 Refresh Token")
        try:
            expires_in = max(60, int(payload.get("expires_in") or 3600))
        except (TypeError, ValueError):
            expires_in = 3600
        rotated_refresh = str(payload.get("refresh_token") or "").strip()
        if rotated_refresh and rotated_refresh != refresh_token:
            saver = getattr(self.config_store, "save_card_config", None)
            if callable(saver):
                try:
                    saver(self.card_id, {"refresh_token": rotated_refresh})
                except Exception:
                    # Keep this operation usable; the next authentication attempt
                    # will explain if the upstream invalidated the previous token.
                    pass
        drive_id = str(config.get("default_drive_id") or payload.get("default_drive_id") or "").strip()
        if not drive_id:
            try:
                user = self._request(
                    "POST",
                    f"{_API}/v2/user/get",
                    headers={**_SHARE_HEADERS, "Authorization": f"Bearer {access_token}"},
                    json={},
                )
                drive_id = str(user.get("default_drive_id") or "").strip()
            except RuntimeError:
                drive_id = ""
        self._access_token = access_token
        self._access_expires_at = time.time() + expires_in
        self._refresh_token = rotated_refresh or refresh_token
        self._drive_id = drive_id
        return access_token, drive_id

    def _auth_headers(self) -> tuple[dict[str, str], str]:
        access_token, drive_id = self._ensure_login()
        if not drive_id:
            raise RuntimeError("无法读取阿里云盘默认 Drive ID；请在卡片配置中手动填写")
        return {**_SHARE_HEADERS, "Authorization": f"Bearer {access_token}"}, drive_id

    def check(self, config: dict | None = None) -> dict[str, Any]:
        saved = config if isinstance(config, dict) else self._config()
        if not str(saved.get("refresh_token") or "").strip():
            return {"status": "unconfigured", "message": "尚未配置阿里云盘 Refresh Token"}
        try:
            # check() receives an explicit config from the UI; the config store is
            # the source of truth for API calls, so validate that the saved value exists.
            self._ensure_login()
            return {"status": "healthy", "message": "阿里云盘认证成功"}
        except Exception as exc:
            return {"status": "unavailable", "message": str(exc)[:240]}

    def _resolve_share(self, resource: object) -> tuple[str, list[dict[str, Any]], str]:
        share_id = _share_id(resource)
        if not share_id:
            raise RuntimeError("阿里云盘分享链接或资源 ID 无效")
        password = (
            str(resource.get("password") or resource.get("passcode") or "").strip()
            if isinstance(resource, dict)
            else ""
        )
        token_data = self._request(
            "POST",
            f"{_API}/v2/share_link/get_share_token",
            headers=_SHARE_HEADERS,
            json={"share_id": share_id, "share_pwd": password},
        )
        share_token = str(token_data.get("share_token") or "").strip()
        if not share_token:
            raise RuntimeError("获取阿里云盘分享 Token 失败，请检查提取码或分享是否失效")
        all_files: list[dict[str, Any]] = []
        visited: set[str] = set()

        def walk(parent_id: str, depth: int) -> None:
            if depth > 5 or parent_id in visited or len(all_files) >= 5000:
                return
            visited.add(parent_id)
            marker = ""
            for _ in range(50):
                body = {
                    "share_id": share_id,
                    "parent_file_id": parent_id,
                    "limit": 100,
                    "marker": marker,
                    "order_by": "name",
                    "order_direction": "ASC",
                }
                data = self._request(
                    "POST",
                    f"{_API}/adrive/v2/file/list_by_share",
                    headers={**_SHARE_HEADERS, "x-share-token": share_token},
                    json=body,
                )
                items = data.get("items") or []
                if not isinstance(items, list):
                    raise RuntimeError("阿里云盘分享文件列表格式异常")
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    file_id = str(item.get("file_id") or "").strip()
                    if not file_id:
                        continue
                    record = {
                        **item,
                        "fid": file_id,
                        "file_name": str(item.get("name") or item.get("file_name") or ""),
                        "size": item.get("size") or 0,
                        "dir_file": item.get("type") == "folder",
                    }
                    if record["dir_file"]:
                        walk(file_id, depth + 1)
                    else:
                        all_files.append(record)
                        if len(all_files) >= 5000:
                            return
                marker = str(data.get("next_marker") or "").strip()
                if not marker:
                    break

        walk("root", 0)
        return share_id, all_files, share_token

    def resolve_resource(self, resource: object) -> dict[str, Any]:
        if not isinstance(resource, dict):
            return {"files": [], "token": None, "error": "资源参数无效"}
        try:
            share_id, files, share_token = self._resolve_share(resource)
            return {
                "files": files,
                "token": share_token,
                "error": None if files else "阿里云盘分享中没有可读取的文件",
                "share_id": share_id,
            }
        except Exception as exc:
            return {"files": [], "token": None, "error": str(exc)[:300]}

    def list_files(self, resource: object) -> list[dict[str, Any]]:
        return self.resolve_resource(resource).get("files") or []

    def destination_options(self) -> list[dict[str, Any]]:
        config = self._config()
        default_id = str(config.get("default_folder_id") or "root")
        options = [{"id": default_id, "name": "默认保存目录", "is_default": True}]
        try:
            headers, drive_id = self._auth_headers()
            marker = ""
            for _ in range(20):
                payload = self._request(
                    "POST",
                    f"{_API}/adrive/v3/file/list",
                    headers=headers,
                    json={
                        "drive_id": drive_id,
                        "parent_file_id": default_id,
                        "limit": 100,
                        "marker": marker,
                        "order_by": "name",
                        "order_direction": "ASC",
                        "type": "folder",
                    },
                )
                for item in payload.get("items") or []:
                    if isinstance(item, dict) and item.get("file_id") and item.get("type") == "folder":
                        options.append({"id": str(item["file_id"]), "name": str(item.get("name") or item["file_id"])})
                marker = str(payload.get("next_marker") or "")
                if not marker:
                    break
        except Exception:
            # Destination discovery is optional; the default destination remains selectable.
            pass
        seen: set[str] = set()
        return [item for item in options if not (item["id"] in seen or seen.add(item["id"]))]

    def create_folder(self, name: str, parent_id: str = "root") -> str:
        folder_name = str(name or "").strip()
        if not folder_name or len(folder_name) > 200:
            raise RuntimeError("文件夹名称不能为空且不能超过 200 个字符")
        headers, drive_id = self._auth_headers()
        parent_id = _folder_id(parent_id)
        # Reuse an existing folder with the same name to avoid duplicate movie folders.
        marker = ""
        for _ in range(20):
            data = self._request(
                "POST",
                f"{_API}/adrive/v3/file/list",
                headers=headers,
                json={
                    "drive_id": drive_id,
                    "parent_file_id": parent_id,
                    "limit": 100,
                    "marker": marker,
                    "order_by": "name",
                    "order_direction": "ASC",
                    "type": "folder",
                },
            )
            for item in data.get("items") or []:
                if isinstance(item, dict) and item.get("type") == "folder" and item.get("name") == folder_name:
                    return str(item.get("file_id") or "")
            marker = str(data.get("next_marker") or "")
            if not marker:
                break
        result = self._request(
            "POST",
            f"{_API}/adrive/v2/file/create",
            headers=headers,
            json={
                "drive_id": drive_id,
                "parent_file_id": parent_id,
                "name": folder_name,
                "type": "folder",
                "check_name_mode": "refuse",
            },
        )
        file_id = str(result.get("file_id") or "").strip()
        if not file_id:
            raise RuntimeError("阿里云盘未返回新目录 ID")
        return file_id

    def transfer(
        self,
        resource: object,
        files: list[dict[str, Any]],
        target_id: str = "root",
    ) -> tuple[bool, str]:
        if not isinstance(resource, dict):
            return False, "资源参数无效"
        share_id = _share_id(resource)
        share_token = str(resource.get("stoken") or "").strip()
        if not share_id or not share_token:
            return False, "阿里云盘分享参数无效或缺少临时 Token"
        try:
            headers, drive_id = self._auth_headers()
            target_id = _folder_id(target_id)
            saved = 0
            failed: list[str] = []
            seen: set[str] = set()
            for item in (files or [])[:200]:
                file_id = str(item.get("fid") or item.get("file_id") or "").strip() if isinstance(item, dict) else ""
                if not file_id or not _ID_RE.fullmatch(file_id) or file_id in seen:
                    continue
                seen.add(file_id)
                try:
                    self._request(
                        "POST",
                        f"{_API}/v2/file/copy",
                        headers={**headers, "x-share-token": share_token},
                        json={
                            "file_id": file_id,
                            "share_id": share_id,
                            "share_token": share_token,
                            "to_drive_id": drive_id,
                            "to_parent_file_id": target_id,
                            "auto_rename": True,
                        },
                    )
                    saved += 1
                except Exception as exc:
                    failed.append(str(exc)[:120])
            if not seen:
                return False, "没有可转存的有效文件"
            if failed:
                if saved:
                    return False, f"部分转存成功 {saved} 个，另有 {len(failed)} 个失败；请先核对网盘结果再重试"
                return False, "阿里云盘转存失败：" + failed[0]
            return True, f"阿里云盘转存成功，共提交 {saved} 个文件"
        except Exception as exc:
            return False, str(exc)[:240]


def create_card(context):
    """Factory used by MovieSync's single-file card loader."""
    return AliyunDriveStorageCard(context["config_store"])
