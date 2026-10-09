"""影视资源检索与转存业务服务。

用途：并发搜索已启用资源源、解析存储目标资源、去重候选资源，并执行用户选择的文件白名单转存。
维护说明：具体平台解析与转存由 StorageTargetCard 负责；核心业务不直接依赖具体网盘平台。
"""
from __future__ import annotations

import re
import threading
from typing import Any

from .resource_sources import ResourceSourceManager
from .storage_targets import StorageTargetManager
from .transfer_outcome import is_uncertain_transfer_message

VIDEO_EXTENSIONS = (".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".m4v", ".ts", ".m2ts", ".iso")
MAX_VIDEO_FILES_PER_CANDIDATE = 200
MAX_CANDIDATES_PER_MOVIE = 20


def _format_size(value: object) -> str:
    try:
        size = int(float(value or 0))
    except (TypeError, ValueError):
        return "未知大小"
    if size <= 0:
        return "未知大小"
    units = ["B", "KB", "MB", "GB", "TB"]
    index = 0
    number = float(size)
    while number >= 1024 and index < len(units) - 1:
        number /= 1024
        index += 1
    return f"{number:.1f} {units[index]}"


def _detect_resolution(name: str) -> str:
    text = str(name or "").lower()
    patterns = [
        (r"\b(2160p|4k|uhd)\b", "4K"),
        (r"\b(1440p|2k)\b", "2K"),
        (r"\b1080[pi]?\b", "1080P"),
        (r"\b(720[pi]?)\b", "720P"),
        (r"\b(480[pi]?)\b", "480P"),
    ]
    for pattern, label in patterns:
        if re.search(pattern, text):
            return label
    return "未知"


class SearchService:
    def __init__(
        self,
        resource_sources: ResourceSourceManager,
        storage_targets: StorageTargetManager,
        logger,
    ):
        self.resource_sources = resource_sources
        self.storage_targets = storage_targets
        self.logger = logger
        self._share_cache: dict[str, tuple[list[dict[str, Any]], str | None, str | None, str]] = {}
        self._share_lock = threading.Lock()

    @staticmethod
    def _title(movie: object) -> tuple[str, str]:
        title = str(movie.get("title", movie.get("name", "")) if isinstance(movie, dict) else movie).strip()
        cleaned = re.sub(r"[\(（]\s*(19\d{2}|20\d{2})\s*[\)）]", "", title).strip()
        return title, cleaned

    @staticmethod
    def _simplify(value: str) -> str:
        return re.sub(r"[^\w\u4e00-\u9fa5]", "", value or "")

    def _get_resource_files(self, resource: dict):
        storage_target_id = str(resource.get("storage_target_id") or "").strip()
        if not storage_target_id:
            getter = getattr(self.storage_targets, "get", None)
            target = getter() if callable(getter) else None
            storage_target_id = target.card_id if target else ""
        pwd_id = str(resource.get("pwd_id") or "").strip()
        if not pwd_id:
            return [], None, "资源标识无效", storage_target_id
        cache_key = f"{storage_target_id}:{pwd_id}"
        with self._share_lock:
            cached = self._share_cache.get(cache_key)
        if cached is not None:
            return cached
        resolved = self.storage_targets.resolve_resource(resource, storage_target_id or None)
        result = (
            resolved.get("files") or [],
            resolved.get("token"),
            resolved.get("error"),
            resolved.get("target_id") or storage_target_id,
        )
        with self._share_lock:
            self._share_cache[cache_key] = result
        return result

    def search_movie_candidates(self, movie: object, config: dict) -> list[dict]:
        title, cleaned_title = self._title(movie)
        if not title:
            return []
        self.logger.info("开始检索《%s》", title)

        discovered = self.resource_sources.search(
            {"title": cleaned_title},
            config,
        )
        candidates: list[dict] = []
        seen_pwd_ids: set[str] = set()

        for source in discovered:
            pwd_id = str(source.get("pwd_id") or "").strip()
            if not pwd_id or pwd_id in seen_pwd_ids:
                continue
            resource = {
                **source,
                "pwd_id": pwd_id,
            }
            files, _stoken, err, storage_target_id = self._get_resource_files(resource)
            if err or not files:
                self.logger.debug(
                    "资源源 %s 命中 %s 但解析失败: %s",
                    source.get("source_name") or source.get("source_id"),
                    pwd_id,
                    err,
                )
                continue

            videos = [
                {
                    "fid": f.get("fid"),
                    "file_name": f.get("file_name", ""),
                    "size": f.get("size", 0),
                    "size_text": _format_size(f.get("size", 0)),
                    "resolution": _detect_resolution(f.get("file_name", "")),
                }
                for f in files
                if f.get("fid")
                and str(f.get("file_name", "")).lower().endswith(VIDEO_EXTENSIONS)
            ][:MAX_VIDEO_FILES_PER_CANDIDATE]

            if not videos:
                continue

            resolutions = {}
            for video in videos:
                resolution = video["resolution"]
                resolutions[resolution] = resolutions.get(resolution, 0) + 1

            total_size = sum(int(v.get("size") or 0) for v in videos)
            seen_pwd_ids.add(pwd_id)
            candidates.append({
                "source_id": source.get("source_id", "unknown"),
                "source_name": source.get("source_name", "未知来源"),
                "cover": str(movie.get("cover", "") if isinstance(movie, dict) else "").strip()[:1000],
                "storage_target_id": storage_target_id,
                "channel": source.get("channel", ""),
                "channel_id": source.get("channel_id", ""),
                "pwd_id": pwd_id,
                "files": videos,
                "file_count": len(videos),
                "total_size": total_size,
                "total_size_text": _format_size(total_size),
                "resolutions": resolutions,
                "summary": (
                    f"来源: [{source.get('source_name', '未知来源')}] | "
                    f"频道: [{source.get('channel', '')}] | "
                    f"{len(videos)} 个视频 | {_format_size(total_size)}"
                ),
            })
            if len(candidates) >= MAX_CANDIDATES_PER_MOVIE:
                break

        self.logger.info("《%s》检索完成，有效候选=%s", title, len(candidates))
        return candidates

    def transfer_selected_resource(
        self,
        movie: object,
        candidate: dict,
        target_fid: str = "0",
        category_fids: dict | None = None,
    ) -> tuple[bool, str]:
        ok, message, _ = self.transfer_selected_resource_with_progress(
            movie, candidate, target_fid, category_fids
        )
        return ok, message

    def transfer_selected_resource_with_progress(
        self,
        movie: object,
        candidate: dict,
        target_fid: str = "0",
        category_fids: dict | None = None,
        progress=None,
    ) -> tuple[bool, str, dict]:
        progress = progress or (lambda *_args: None)
        title, _ = self._title(movie)
        tag = str(movie.get("tag", "电影")) if isinstance(movie, dict) else "电影"
        # 前端传入 target_fid 即表示用户明确选择了目标目录；分类目录仅作为资源选择页的默认值。
        # 不再在服务层强制覆盖用户选择，避免“下拉框看似可选但实际始终按分类目录转存”。
        parent_fid = str(target_fid or (category_fids or {}).get(tag) or "0").strip() or "0"
        pwd_id = str(candidate.get("pwd_id") or "").strip()
        selected_fids = [
            str(item.get("fid"))
            for item in candidate.get("files", [])
            if isinstance(item, dict) and item.get("fid")
        ]
        selected_fids = list(dict.fromkeys(selected_fids))
        total = len(selected_fids)
        if not pwd_id or not selected_fids:
            return False, "候选资源参数无效", {"success": 0, "skipped": 0, "failed": total}

        storage_target_id = str(candidate.get("storage_target_id") or "").strip()
        resource = {
            **candidate,
            "pwd_id": pwd_id,
            "storage_target_id": storage_target_id,
        }
        progress(20, "正在重新验证分享资源…")
        files, fresh_stoken, err, storage_target_id = self._get_resource_files(resource)
        if err or not files or not fresh_stoken:
            return False, f"分享资源解析失败: {err or '未知错误'}", {"success": 0, "skipped": 0, "failed": total}
        available_fids = {str(item.get("fid")) for item in files if item.get("fid")}
        if not set(selected_fids).issubset(available_fids):
            return False, "所选文件已不存在或不属于该分享资源", {"success": 0, "skipped": 0, "failed": total}

        progress(45, "正在准备目标文件夹…")
        try:
            folder_fid = self.storage_targets.create_folder(
                title,
                parent_fid,
                storage_target_id or None,
            )
            create_err = None
        except Exception as exc:
            folder_fid = None
            create_err = str(exc)
        if not folder_fid:
            return False, f"创建专属文件夹失败: {create_err}", {"success": 0, "skipped": 0, "failed": total}

        progress(70, f"正在转存 {total} 个文件…")
        ok, msg = self.storage_targets.transfer(
            resource,
            [{"fid": fid} for fid in selected_fids],
            folder_fid,
            storage_target_id or None,
            fresh_stoken,
        )
        if ok:
            self.logger.info("《%s》转存成功，pwd_id=%s", title, pwd_id)
            progress(100, "转存完成")
            return True, f"《{title}》转存成功！已精准归档至专属文件夹", {"success": total, "skipped": 0, "failed": 0}
        self.logger.warning("《%s》转存失败: %s", title, msg)
        uncertain = is_uncertain_transfer_message(msg)
        return False, f"转存失败: {msg}", {
            "success": 0,
            "skipped": 0,
            "failed": total,
            "uncertain": uncertain,
        }

