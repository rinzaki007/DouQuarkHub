"""自动追剧任务管理器。

用途：周期性检查资源源中的新内容，并通过选定的存储目标完成归档。

用途：创建/删除/立即执行订阅任务，并在后台周期性检查夸克分享中的新集数或指定文件。
维护说明：订阅会持久化到 data/subscriptions.json；每次执行都会重新获取分享 Token，并再次校验目标 FID。
"""
from __future__ import annotations

import re
import time
import uuid
from datetime import datetime
from threading import Event, RLock, Thread

from ..storage import JsonStore

SUBSCRIPTION_SCHEMA_VERSION = 4
VIDEO_EXTENSIONS = (".mp4", ".mkv", ".avi", ".mov", ".flv", ".wmv", ".m4v", ".ts", ".m2ts", ".iso")


def _normalize_resource_id(value: object) -> str:
    value = str(value or "").strip()
    if len(value) > 128 or (value and not all(char.isalnum() or char in "_-" for char in value)):
        raise ValueError("分享资源 ID 无效")
    return value

def _clean_tv_filename(file_name: str, title: str = "") -> tuple[int | None, str]:
    if not file_name:
        return None, file_name
    patterns = [
        r"\bS\d{1,2}E(\d{1,4})\b",
        r"\bEP?\s*(\d{1,4})\b",
        r"第\s*(\d{1,4})\s*[集话期]",
        r"[\[(【](\d{1,4})[\])】]",
    ]
    for pattern in patterns:
        match = re.search(pattern, file_name, re.IGNORECASE)
        if not match:
            continue
        episode = int(match.group(1))
        if 1900 <= episode <= 2030 or episode in {720, 1080, 2160}:
            continue
        return episode, file_name
    return None, file_name

def _normalize_fid(value: object) -> str:
    fid = str(
        value or ""
    ).strip()

    if not fid:
        return "0"

    if len(fid) > 128:
        raise ValueError(
            "目标存储目录 FID 不能超过 128 个字符"
        )

    if not all(
        char.isalnum() or char in "_-"
        for char in fid
    ):
        raise ValueError(
            "目标存储目录 FID 格式无效"
        )

    return fid


class SubscriptionManager:
    def __init__(
        self,
        subscriptions_file,
        storage_targets,
        resource_sources=None,
        logger=None,
        max_interval_hours: int = 168,
    ):
        # 兼容旧调用方式：SubscriptionManager(file, storage_target, logger)
        if logger is None:
            logger = resource_sources
            resource_sources = None
        self.store = JsonStore(
            subscriptions_file,
            lambda: [],
        )

        self.storage_targets = storage_targets
        self.resource_sources = resource_sources
        self.config_store = getattr(resource_sources, "config_store", None)
        self.logger = logger
        self.max_interval_hours = (
            max_interval_hours
        )

        self.lock = RLock()
        self.running_ids: set[str] = set()
        self.stop_event = Event()
        self.worker: Thread | None = None
        self.schema_version = SUBSCRIPTION_SCHEMA_VERSION

    @staticmethod
    def _now_string() -> str:
        return datetime.now().strftime(
            "%Y-%m-%d %H:%M"
        )

    def _load_subscriptions(self) -> list[dict]:
        data = self.store.read()

        if not isinstance(data, list):
            data = []

        changed = False
        normalized = []

        for item in data:
            if not isinstance(item, dict):
                changed = True
                continue

            item = dict(item)

            try:
                version = int(
                    item.get(
                        "schema_version",
                        1,
                    )
                )
            except (TypeError, ValueError):
                version = 1

            if version < 2:
                item.setdefault("retry_count", 0)
                item.setdefault("pending_save_keys", [])
                changed = True

            item["schema_version"] = SUBSCRIPTION_SCHEMA_VERSION
            item.setdefault("storage_target_id", "")
            item.setdefault("cover", "")
            item.setdefault("source_id", "")
            item.setdefault("initial_file_keys", [])
            item.setdefault("tracking_mode", "legacy")
            item.setdefault("status", "waiting")
            item.setdefault("phase", "waiting")
            item.setdefault("phase_label", "等待下次检查")
            tracked = item.get("tracked_file_keys")
            if not isinstance(tracked, list):
                item["tracked_file_keys"] = []
                changed = True
            item["tracked_file_keys"] = list(dict.fromkeys(
                str(key).strip()
                for key in item.get("tracked_file_keys", [])
                if str(key).strip()
            ))[:1000]
            item.setdefault("run_history", [])
            if not isinstance(item["run_history"], list):
                item["run_history"] = []
                changed = True
            item["run_history"] = item["run_history"][-50:]
            item["pending_save_keys"] = [
                str(key)
                for key in (
                    item.get("pending_save_keys", [])
                    or []
                )
                if str(key).strip()
            ][:200]

            normalized.append(item)

        if changed or normalized != data:
            self.store.write(normalized)

        return normalized

    def get_subscriptions(
        self,
    ) -> list[dict]:
        with self.lock:
            return list(self._load_subscriptions())

    def add_subscription(
        self,
        *,
        title: str,
        pwd_id: str,
        target_fid: str = "0",
        interval_hours: int = 6,
        start_ep: int = 0,
        channel: str = "",
        channel_name: str = "",
        files=None,
        storage_target_id: str = "",
        cover: str = "",
        source_id: str = "",
    ) -> dict:
        title = str(
            title or ""
        ).strip()

        if not 1 <= len(title) <= 200:
            raise ValueError(
                "追剧名称长度必须在 1-200 个字符之间"
            )

        pwd_id = _normalize_resource_id(pwd_id)
        if not pwd_id:
            raise ValueError("分享资源 ID 无效")

        target_fid = _normalize_fid(
            target_fid
        )

        interval_hours = int(
            interval_hours
        )

        start_ep = max(
            0,
            int(start_ep),
        )

        if not (
            1
            <= interval_hours
            <= self.max_interval_hours
        ):
            raise ValueError(
                "检测周期必须在 "
                f"1-{self.max_interval_hours} "
                "小时之间"
            )

        target_fids = []
        selected_episode_numbers: list[int] = []
        seen = set()

        for item in (files or [])[:200]:
            fid = str(
                item.get("fid")
                if isinstance(
                    item,
                    dict,
                )
                else item
                or ""
            ).strip()

            if (
                fid
                and len(fid) <= 128
                and all(
                    char.isalnum() or char in "_-"
                    for char in fid
                )
                and fid not in seen
            ):
                seen.add(fid)
                target_fids.append(fid)
                ep_num, _ = _clean_tv_filename(
                    str(item.get("file_name") or "")
                    if isinstance(item, dict)
                    else "",
                    title,
                )
                if ep_num is not None:
                    selected_episode_numbers.append(ep_num)

        subscription = {
            "id": uuid.uuid4().hex,
            "title": title,
            "pwd_id": pwd_id,
            "target_fid": target_fid,
            "storage_target_id": str(storage_target_id or "").strip(),
            "interval_hours": interval_hours,
            "start_ep": max([start_ep, *selected_episode_numbers], default=start_ep),
            "channel": str(
                channel or ""
            ).strip()[:100],
            "channel_name": str(
                channel_name or channel or ""
            ).strip()[:100],
            "source_id": str(source_id or "").strip()[:100],
            "cover": str(cover or "").strip()[:1000],
            "tracking_mode": (
                "channel"
                if source_id and channel
                else ("all" if target_fids else "legacy")
            ),
            "status": "waiting",
            "phase": "waiting",
            "phase_label": "等待下次检查",
            "tracked_file_keys": (
                [f"{pwd_id}:{fid}" for fid in target_fids]
                if source_id and channel
                else target_fids
            ),
            "initial_file_keys": target_fids,
            "files": [],
            "saved_episodes": [],
            "last_check": "从未检测",
            "last_check_at": None,
            "next_run_at": time.time(),
            "last_error": "",
            "retry_count": 0,
            "pending_save_keys": [],
            "run_history": [],
            "schema_version": SUBSCRIPTION_SCHEMA_VERSION,
        }

        with self.lock:
            subscriptions = self._load_subscriptions()

            subscription["schema_version"] = SUBSCRIPTION_SCHEMA_VERSION
            subscription["pending_save_keys"] = []

            subscriptions.append(
                subscription
            )

            self.store.write(
                subscriptions
            )

        return subscription

    def delete_subscription(
        self,
        sub_id: str,
    ) -> bool:
        sub_id = str(sub_id)
        with self.lock:
            if sub_id in self.running_ids:
                return False
            subscriptions = self._load_subscriptions()

            new_subscriptions = [
                item
                for item in subscriptions
                if item.get("id")
                != str(sub_id)
            ]

            changed = (
                len(new_subscriptions)
                != len(subscriptions)
            )

            if changed:
                self.store.write(
                    new_subscriptions
                )

            return changed

    def clear_run_history(self) -> int:
        with self.lock:
            subscriptions = self._load_subscriptions()
            removed = 0
            changed = False
            for item in subscriptions:
                history = item.get("run_history") or []
                if history:
                    removed += len(history)
                    item["run_history"] = []
                    changed = True
            if changed:
                self.store.write(subscriptions)
            return removed

    def check_subscription_now(
        self,
        sub_id: str,
    ) -> tuple[bool, str]:
        with self.lock:
            subscriptions = self._load_subscriptions()

            subscription = next(
                (
                    item
                    for item in subscriptions
                    if item.get("id")
                    == str(sub_id)
                ),
                None,
            )

        if not subscription:
            return (
                False,
                "未找到订阅任务",
            )

        sub_id = str(sub_id)

        with self.lock:
            if sub_id in self.running_ids:
                return (
                    False,
                    "该订阅正在执行，请稍后再试",
                )

            self.running_ids.add(
                sub_id
            )

        self._set_status(
            subscription,
            "running",
            "searching",
            "正在搜刮频道资源…",
        )
        try:
            return self._check(
                subscription
            )

        except Exception as exc:
            self.logger.exception(
                "订阅任务 %s 执行异常",
                sub_id,
            )

            return self._finish(
                subscription,
                False,
                f"任务执行异常: {exc}",
            )

        finally:
            with self.lock:
                self.running_ids.discard(
                    sub_id
                )

    def _set_status(self, sub: dict, status: str, phase: str, phase_label: str) -> None:
        with self.lock:
            subscriptions = self._load_subscriptions()
            current = next(
                (item for item in subscriptions if item.get("id") == sub.get("id")),
                None,
            )
            if current is None:
                return
            current["status"] = status
            current["phase"] = phase
            current["phase_label"] = phase_label
            if status == "running":
                current["last_error"] = ""
            self.store.write(subscriptions)

    def _check(
        self,
        sub: dict,
    ) -> tuple[bool, str]:
        if sub.get("tracking_mode") == "channel" and sub.get("source_id") and sub.get("channel"):
            return self._check_channel_subscription(sub)

        resource = {
            "pwd_id": str(sub.get("pwd_id") or "").strip(),
            "storage_target_id": str(sub.get("storage_target_id") or "").strip(),
        }
        resolved = self.storage_targets.resolve_resource(
            resource,
            resource.get("storage_target_id") or None,
        )
        files = resolved.get("files") or []
        fetched_stoken = resolved.get("token")
        target_id = str(
            resolved.get("target_id")
            or resource.get("storage_target_id")
            or ""
        ).strip()
        err = resolved.get("error")

        if err or not files or not fetched_stoken:
            return self._finish(sub, False, f"解析链接失败: {err or '未找到文件'}")

        tracked_keys = {
            str(key).strip()
            for key in (sub.get("tracked_file_keys", []) or [])
            if str(key).strip()
        }
        selected = []
        found_keys = []
        if sub.get("tracking_mode") == "all":
            for item in files:
                fid = str(item.get("fid") or "").strip()
                if fid and fid not in tracked_keys:
                    selected.append({"fid": fid})
                    found_keys.append(fid)
        elif sub.get("files"):
            saved = {
                item for item in (sub.get("saved_episodes", []) or [])
                if isinstance(item, (str, int))
            }
            target_fids = {
                str(item.get("fid"))
                for item in (sub.get("files") or [])
                if isinstance(item, dict) and item.get("fid")
            }
            for item in files:
                fid = str(item.get("fid") or "")
                if fid in target_fids and fid not in saved:
                    selected.append({"fid": fid})
                    found_keys.append(fid)
        else:
            saved = {
                item for item in (sub.get("saved_episodes", []) or [])
                if isinstance(item, (str, int))
            }
            start_ep = int(sub.get("start_ep", 0) or 0)
            for item in files:
                ep_num, _ = _clean_tv_filename(
                    str(item.get("file_name", "")),
                    str(sub.get("title", "")),
                )
                if ep_num is not None and ep_num > start_ep and ep_num not in saved:
                    selected.append({"fid": item.get("fid")})
                    found_keys.append(ep_num)

        if not selected:
            return self._finish(sub, True, f"《{sub.get('title', '')}》暂无新更新", success_keys=[])

        target_fid = _normalize_fid(sub.get("target_fid"))
        try:
            folder_fid = self.storage_targets.create_folder(
                str(sub.get("title", "")),
                target_fid,
                target_id or None,
            )
        except Exception as exc:
            return self._finish(sub, False, f"创建专属文件夹失败: {exc}")

        pending_keys = list(dict.fromkeys(str(key) for key in found_keys))[:200]
        with self.lock:
            subscriptions = self._load_subscriptions()
            current = next((item for item in subscriptions if item.get("id") == sub.get("id")), None)
            if current is not None:
                current["pending_save_keys"] = pending_keys
                current["storage_target_id"] = target_id
                self.store.write(subscriptions)

        ok, msg = self.storage_targets.transfer(
            resource,
            selected,
            folder_fid,
            target_id or None,
            fetched_stoken,
        )
        if not ok:
            return self._finish(sub, False, f"转存失败: {msg}")

        return self._finish(
            sub,
            True,
            f"🎉 成功追更 {len(found_keys)} 项，已存入专属文件夹【{sub.get('title', '')}】！",
            success_keys=found_keys,
        )

    def _check_channel_subscription(self, sub: dict) -> tuple[bool, str]:
        source_id = str(sub.get("source_id") or "").strip()
        channel = str(sub.get("channel") or "").strip()
        title = str(sub.get("title") or "").strip()
        self._set_status(sub, "running", "searching", "正在搜刮频道资源…")
        sources = (
            self.resource_sources.search_channel(source_id, channel, title)
            if self.resource_sources
            else []
        )

        if not sources:
            return self._finish(sub, True, f"《{title}》频道暂未发现新资源", success_keys=[])

        tracked = {
            str(key).strip()
            for key in (sub.get("tracked_file_keys", []) or [])
            if str(key).strip()
        }
        baseline_episode = int(sub.get("start_ep", 0) or 0)
        grouped: dict[tuple[str, str], dict] = {}

        for source in sources:
            self._set_status(sub, "running", "resolve", "正在解析发现的资源…")
            pwd_id = str(source.get("pwd_id") or "").strip()
            if not pwd_id:
                continue
            resource = {
                **source,
                "pwd_id": pwd_id,
                "storage_target_id": str(
                    source.get("storage_target_id")
                    or sub.get("storage_target_id")
                    or ""
                ).strip(),
            }
            resolved = self.storage_targets.resolve_resource(
                resource,
                resource.get("storage_target_id") or None,
            )
            files = resolved.get("files") or []
            token = resolved.get("token")
            target_id = str(
                resolved.get("target_id")
                or resource.get("storage_target_id")
                or ""
            ).strip()
            if resolved.get("error") or not files or not token:
                continue

            for item in files:
                fid = str(item.get("fid") or "").strip()
                if not fid:
                    continue
                key = f"{pwd_id}:{fid}"
                if key in tracked:
                    continue
                file_name = str(item.get("file_name") or "")
                if not file_name.lower().endswith(VIDEO_EXTENSIONS):
                    continue
                episode, _ = _clean_tv_filename(file_name, title)
                if episode is None:
                    continue
                if episode < baseline_episode:
                    continue
                grouped.setdefault((pwd_id, target_id), {
                    "resource": resource,
                    "token": token,
                    "target_id": target_id,
                    "files": [],
                    "keys": [],
                })["files"].append({"fid": fid})
                grouped[(pwd_id, target_id)]["keys"].append(key)

        if not grouped:
            return self._finish(sub, True, f"《{title}》暂无新更新", success_keys=[])

        target_fid = _normalize_fid(sub.get("target_fid"))
        try:
            default_target = next(iter(grouped.values()))
            folder_fid = self.storage_targets.create_folder(
                title,
                target_fid,
                default_target["target_id"] or None,
            )
        except Exception as exc:
            return self._finish(sub, False, f"创建专属文件夹失败: {exc}")

        all_keys: list[str] = []
        total = 0
        self._set_status(sub, "running", "transfer", "正在转存新资源…")
        for group in grouped.values():
            ok, msg = self.storage_targets.transfer(
                group["resource"],
                group["files"],
                folder_fid,
                group["target_id"] or None,
                group["token"],
            )
            if not ok:
                return self._finish(sub, False, f"转存失败: {msg}")
            all_keys.extend(group["keys"])
            total += len(group["files"])

        return self._finish(
            sub,
            True,
            f"🎉 成功追更 {total} 项，已存入专属文件夹【{title}】！",
            success_keys=all_keys,
        )

    def _finish(
        self,
        sub: dict,
        success: bool,
        message: str,
        success_keys=None,
    ) -> tuple[bool, str]:
        success_keys = (
            success_keys or []
        )

        with self.lock:
            subscriptions = self._load_subscriptions()

            current = next(
                (
                    item
                    for item in subscriptions
                    if item.get("id")
                    == sub.get("id")
                ),
                None,
            )

            if current is None:
                return (
                    success,
                    message,
                )

            current["status"] = "success" if success else "failed"
            current["phase"] = "completed" if success else "failed"
            current["phase_label"] = "检查完成" if success else "检查失败"
            current["last_check"] = (
                self._now_string()
                + (
                    " (成功)"
                    if success
                    else " (失败)"
                )
            )

            current["last_check_at"] = (
                time.time()
            )

            try:
                interval_hours = int(
                    current.get(
                        "interval_hours",
                        6,
                    )
                )
            except (TypeError, ValueError):
                interval_hours = 6

            interval_hours = max(
                1,
                min(
                    self.max_interval_hours,
                    interval_hours,
                ),
            )

            current["interval_hours"] = interval_hours

            if success:
                current["retry_count"] = 0
                current["pending_save_keys"] = []
                delay_seconds = interval_hours * 3600
            else:
                try:
                    retry_count = int(
                        current.get(
                            "retry_count",
                            0,
                        )
                    )
                except (TypeError, ValueError):
                    retry_count = 0

                retry_count = max(0, retry_count) + 1
                current["retry_count"] = retry_count

                # 临时故障采用短退避，连续失败再逐步拉长，
                # 但不会超过用户设置的正常检测周期。
                delay_seconds = min(
                    interval_hours * 3600,
                    300 * (2 ** min(retry_count - 1, 6)),
                )

            current["next_run_at"] = (
                time.time() + delay_seconds
            )

            current["last_error"] = (
                ""
                if success
                else message
            )
            history = current.get("run_history", [])
            if not isinstance(history, list):
                history = []
            history.append({
                "at": time.time(),
                "success": bool(success),
                "message": str(message)[:500],
                "success_count": len(success_keys) if success else 0,
                "failed_count": 0 if success else 1,
            })
            current["run_history"] = history[-50:]

            if success_keys:
                tracked = list(current.get("tracked_file_keys", []) or [])
                seen_tracked = set(str(key) for key in tracked)
                tracked.extend(
                    str(key) for key in success_keys
                    if str(key) not in seen_tracked
                )
                current["tracked_file_keys"] = tracked[-1000:]

                old = list(
                    current.get(
                        "saved_episodes",
                        [],
                    )
                )

                seen = set(old)

                old.extend(
                    key
                    for key in success_keys
                    if key not in seen
                )

                current[
                    "saved_episodes"
                ] = sorted(
                    old,
                    key=lambda value: (
                        isinstance(
                            value,
                            str,
                        ),
                        str(value),
                    ),
                )

            self.store.write(
                subscriptions
            )

        if success:
            self.logger.info(
                message
            )
        else:
            self.logger.warning(
                message
            )

        return (
            success,
            message,
        )

    def start_scheduler(
        self,
    ) -> None:
        with self.lock:
            if (
                self.worker
                and self.worker.is_alive()
            ):
                return

            self.stop_event.clear()

            self.worker = Thread(
                target=self._scheduler_loop,
                name="moviesync-scheduler",
                daemon=True,
            )

            self.worker.start()

        self.logger.info(
            "自动追剧调度器已启动"
        )

    def stop_scheduler(
        self,
    ) -> None:
        self.stop_event.set()

        worker = self.worker

        if (
            worker
            and worker.is_alive()
        ):
            worker.join(
                timeout=2
            )

        self.worker = None

    def _scheduler_loop(
        self,
    ) -> None:
        while not self.stop_event.wait(30):
            try:
                subscriptions = self.get_subscriptions()
            except Exception as exc:
                self.logger.exception(
                    "读取自动追剧任务失败: %s",
                    exc,
                )
                continue

            now = time.time()

            for sub in subscriptions:
                try:
                    next_run_at = float(
                        sub.get(
                            "next_run_at",
                            0,
                        )
                        or 0
                    )
                except (TypeError, ValueError):
                    next_run_at = 0

                if next_run_at > now:
                    continue

                try:
                    self.check_subscription_now(
                        str(sub.get("id") or "")
                    )
                except Exception:
                    self.logger.exception(
                        "自动追剧任务调度异常: %s",
                        sub.get("id"),
                    )
