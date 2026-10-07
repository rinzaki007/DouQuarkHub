"""夸克网盘 API 客户端。

用途：校验 Cookie、解析分享文件、创建分类/影视专属目录，以及执行白名单文件转存。
维护说明：分享解析限制递归深度和文件数量；转存只接收经过服务端重新解析并校验过的文件 FID。
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from .http import ApiError, HttpClient


QUARK_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://pan.quark.cn/",
    "Origin": "https://pan.quark.cn",
    "Content-Type": "application/json",
}
VIDEO_EXTENSIONS = (".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".m4v", ".ts", ".m2ts", ".iso")


def sanitize_pwd_id(pwd_id: object) -> str:
    if not pwd_id:
        return ""
    value = str(pwd_id).strip()
    match = re.search(r"quark\.cn/s/([A-Za-z0-9]+)", value, re.IGNORECASE)
    if match:
        return match.group(1)
    if "://" in value or "/" in value or "?" in value:
        return ""
    return value if re.fullmatch(r"[A-Za-z0-9]{1,128}", value) else ""


def clean_tv_filename(raw_name: str, title: str = "") -> tuple[int | None, str]:
    if not raw_name:
        return None, raw_name
    patterns = [
        r"\bS\d{1,2}E(\d{1,4})\b",
        r"\bEP?\s*(\d{1,4})\b",
        r"第\s*(\d{1,4})\s*[集话期]",
        r"[\[(【](\d{1,4})[\])】]",
    ]
    for pattern in patterns:
        match = re.search(pattern, raw_name, re.IGNORECASE)
        if not match:
            continue
        episode = int(match.group(1))
        if 1900 <= episode <= 2030 or episode in {720, 1080, 2160}:
            continue
        return episode, raw_name
    return None, raw_name


class QuarkClient:
    def __init__(self, cookie: str):
        cookie = "".join((cookie or "").splitlines()).strip()
        if cookie.lower().startswith("cookie:"):
            cookie = cookie[7:].strip()
        self.cookie = cookie
        headers = {**QUARK_HEADERS, "Cookie": cookie}
        self.http = HttpClient(headers)

    def check_cookie_valid(self) -> bool:
        if not self.cookie:
            return False
        try:
            response, data = self.http.request_json(
                "GET",
                "https://drive.quark.cn/1/clouddrive/file/sort?pr=ucpro&fr=pc&pdir_fid=0&num=1",
                timeout=6,
                retries=1,
            )
            return response.status_code == 200 and data.get("code") == 0
        except ApiError:
            return False

    def _list_children(self, parent_fid: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page = 1
        while page <= 20:
            url = (
                "https://drive.quark.cn/1/clouddrive/file/sort"
                f"?pr=ucpro&fr=pc&pdir_fid={quote(str(parent_fid))}&p={page}&num=200"
            )
            try:
                response, data = self.http.request_json("GET", url, timeout=6, retries=1)
            except ApiError:
                break
            if response.status_code != 200 or data.get("code") != 0:
                break
            batch = data.get("data", {}).get("list", []) or []
            items.extend(batch)
            if len(batch) < 200:
                break
            page += 1
        return items

    def get_or_create_subfolder(self, folder_name: str, parent_fid: str = "0") -> tuple[str | None, str | None]:
        parent_fid = str(parent_fid or "0").strip()
        folder_name = str(folder_name or "").strip()
        if not folder_name:
            return None, "文件夹名称不能为空"

        for item in self._list_children(parent_fid):
            is_dir = item.get("dir_file") is True or item.get("file_type") == 0
            if is_dir and item.get("file_name") == folder_name and item.get("fid"):
                return str(item["fid"]), None

        url = "https://drive-pc.quark.cn/1/clouddrive/file?pr=ucpro&fr=pc"
        payload = {"pdir_fid": parent_fid, "file_name": folder_name, "dir_init_lock": False, "dir_path": ""}
        error_message = "创建目录失败"
        try:
            response, data = self.http.request_json("POST", url, timeout=8, retries=0, json=payload)
            if response.status_code == 200 and data.get("code") == 0:
                obj = data.get("data") or {}
                fid = obj.get("fid") or obj.get("file_id") or data.get("fid")
                if fid:
                    return str(fid), None
            error_message = str(data.get("message") or f"HTTP {response.status_code}")
        except ApiError as exc:
            error_message = str(exc)

        for item in self._list_children(parent_fid):
            is_dir = item.get("dir_file") is True or item.get("file_type") == 0
            if is_dir and item.get("file_name") == folder_name and item.get("fid"):
                return str(item["fid"]), None
        return None, error_message

    def get_share_files(
        self,
        pwd_id: object,
        max_depth: int = 3,
        max_files: int = 5000,
    ) -> tuple[
        list[dict[str, Any]] | None,
        str | None,
        str | None,
    ]:
        pwd_id = sanitize_pwd_id(pwd_id)
        if not pwd_id:
            return None, None, "分享链接 ID 无效"

        token_url = "https://drive.quark.cn/1/clouddrive/share/sharepage/token"
        try:
            response, data = self.http.request_json(
                "POST", token_url, timeout=8, retries=1, json={"pwd_id": pwd_id, "passcode": ""}
            )
            if response.status_code == 404:
                return None, None, "分享链接已失效或已被删除"
            if response.status_code != 200 or data.get("code") != 0:
                return None, None, str(data.get("message") or f"获取 Token 失败（HTTP {response.status_code}）")
            stoken = (data.get("data") or {}).get("stoken")
        except ApiError as exc:
            return None, None, f"请求 Token 失败: {exc}"

        if not stoken:
            return None, None, "上游未返回 stoken"

        all_files: list[dict[str, Any]] = []
        visited: set[str] = set()

        def walk(parent_fid: str, depth: int) -> None:
            if depth > max_depth or len(all_files) >= max_files or parent_fid in visited:
                return
            visited.add(parent_fid)
            page = 1
            while page <= 20 and len(all_files) < max_files:
                url = (
                    "https://drive.quark.cn/1/clouddrive/share/sharepage/detail"
                    f"?pr=ucpro&fr=pc&pwd_id={quote(pwd_id)}"
                    f"&stoken={quote(stoken, safe='')}"
                    f"&pdir_fid={quote(str(parent_fid))}&p={page}&num=200"
                )
                try:
                    response, payload = self.http.request_json("GET", url, timeout=8, retries=1)
                except ApiError:
                    return
                if response.status_code != 200 or payload.get("code") != 0:
                    return
                batch = payload.get("data", {}).get("list", []) or []
                for item in batch:
                    if item.get("dir_file") is True or item.get("file_type") == 0:
                        fid = item.get("fid")
                        if fid:
                            walk(str(fid), depth + 1)
                    else:
                        all_files.append(item)
                        if len(all_files) >= max_files:
                            return
                if len(batch) < 200:
                    break
                page += 1

        walk("0", 0)
        return all_files, str(stoken), None

    def save_files(
        self,
        pwd_id: object,
        files_to_save: list[dict[str, Any]],
        stoken: str | None,
        target_fid: object = "0",
    ) -> tuple[bool, str]:
        pwd_id = sanitize_pwd_id(pwd_id)
        if not pwd_id:
            return False, "分享链接 ID 无效"
        if not stoken:
            return False, "缺少分享 Token"
        fid_list: list[str] = []
        seen: set[str] = set()
        for item in files_to_save or []:
            fid = str(item.get("fid") or "").strip()
            if fid and fid not in seen:
                seen.add(fid)
                fid_list.append(fid)
        if not fid_list:
            return False, "没有可转存的文件"

        url = "https://drive.quark.cn/1/clouddrive/share/sharepage/save?pr=ucpro&fr=pc"
        payload = {"pwd_id": pwd_id, "stoken": stoken, "fid_list": fid_list, "to_pdir_fid": str(target_fid or "0")}
        try:
            response, data = self.http.request_json("POST", url, timeout=10, retries=0, json=payload)
            if response.status_code == 200 and data.get("code") == 0:
                return True, "转存成功"
            return False, str(data.get("message") or f"转存失败（HTTP {response.status_code}）")
        except ApiError as exc:
            return False, str(exc)
