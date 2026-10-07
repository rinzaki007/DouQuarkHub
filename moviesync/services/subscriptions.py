"""自动追剧任务管理器。

用途：创建/删除/立即执行订阅任务，并在后台周期性检查夸克分享中的新集数或指定文件。
维护说明：订阅会持久化到 data/subscriptions.json；每次执行都会重新获取分享 Token，并再次校验目标 FID。
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime
from threading import Event, RLock, Thread
from typing import Callable

from ..clients.quark import QuarkClient, clean_tv_filename, sanitize_pwd_id
from ..storage import JsonStore


SUBSCRIPTION_SCHEMA_VERSION = 2


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
        get_cookie: Callable[[], str],
        logger,
        max_interval_hours: int = 168,
    ):
        self.store = JsonStore(
            subscriptions_file,
            lambda: [],
        )

        self.get_cookie = get_cookie
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
        files=None,
    ) -> dict:
        title = str(
            title or ""
        ).strip()

        if not 1 <= len(title) <= 200:
            raise ValueError(
                "追剧名称长度必须在 1-200 个字符之间"
            )

        pwd_id = sanitize_pwd_id(pwd_id)

        if not pwd_id:
            raise ValueError(
                "分享链接 ID 无效"
            )

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

        subscription = {
            "id": uuid.uuid4().hex,
            "title": title,
            "pwd_id": pwd_id,
            "target_fid": target_fid,
            "interval_hours": interval_hours,
            "start_ep": start_ep,
            "channel": str(
                channel or ""
            ).strip()[:100],
            "files": [
                {
                    "fid": fid
                }
                for fid in target_fids
            ],
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

    def _check(
        self,
        sub: dict,
    ) -> tuple[bool, str]:
        cookie = (
            self.get_cookie()
            .strip()
        )

        if not cookie:
            return self._finish(
                sub,
                False,
                "缺少夸克 Cookie",
            )

        engine = QuarkClient(
            cookie
        )

        (
            files,
            fetched_stoken,
            err,
        ) = engine.get_share_files(
            sub.get("pwd_id")
        )

        if (
            err
            or not files
            or not fetched_stoken
        ):
            return self._finish(
                sub,
                False,
                "解析链接失败: "
                f"{err or '未找到文件'}",
            )

        saved = {
            item
            for item in (
                sub.get(
                    "saved_episodes",
                    [],
                )
                or []
            )
            if isinstance(item, (str, int))
        }

        selected = []
        found_keys = []

        target_files = (
            sub.get("files")
            or []
        )

        if target_files:
            target_fids = {
                str(
                    item.get("fid")
                )
                for item in target_files
                if (
                    isinstance(
                        item,
                        dict,
                    )
                    and item.get("fid")
                )
            }

            for item in files:
                fid = str(
                    item.get("fid")
                    or ""
                )

                if (
                    fid in target_fids
                    and fid not in saved
                ):
                    selected.append(
                        {
                            "fid": fid
                        }
                    )

                    found_keys.append(
                        fid
                    )

        else:
            start_ep = int(
                sub.get(
                    "start_ep",
                    0,
                )
                or 0
            )

            for item in files:
                ep_num, _ = (
                    clean_tv_filename(
                        str(
                            item.get(
                                "file_name",
                                "",
                            )
                        ),
                        str(
                            sub.get(
                                "title",
                                "",
                            )
                        ),
                    )
                )

                if (
                    ep_num is not None
                    and ep_num > start_ep
                    and ep_num not in saved
                ):
                    selected.append(
                        {
                            "fid": item.get(
                                "fid"
                            )
                        }
                    )

                    found_keys.append(
                        ep_num
                    )

        if not selected:
            return self._finish(
                sub,
                True,
                (
                    f"《{sub.get('title', '')}》"
                    "暂无新更新"
                ),
                success_keys=[],
            )

        target_fid = _normalize_fid(
            sub.get(
                "target_fid"
            )
        )

        folder_fid, folder_err = (
            engine.get_or_create_subfolder(
                str(
                    sub.get(
                        "title",
                        "",
                    )
                ),
                target_fid,
            )
        )

        if not folder_fid:
            return self._finish(
                sub,
                False,
                (
                    "创建专属文件夹失败: "
                    f"{folder_err or '未知错误'}"
                ),
            )

        pending_keys = list(
            dict.fromkeys(
                str(key)
                for key in found_keys
            )
        )[:200]

        with self.lock:
            subscriptions = self._load_subscriptions()
            current = next(
                (
                    item
                    for item in subscriptions
                    if item.get("id") == sub.get("id")
                ),
                None,
            )
            if current is not None:
                current["pending_save_keys"] = pending_keys
                self.store.write(subscriptions)

        ok, msg = engine.save_files(
            sub.get("pwd_id"),
            selected,
            fetched_stoken,
            folder_fid,
        )

        if not ok:
            return self._finish(
                sub,
                False,
                f"转存失败: {msg}",
            )

        return self._finish(
            sub,
            True,
            (
                f"🎉 成功追更 "
                f"{len(found_keys)} 项，"
                "已存入专属文件夹"
                f"【{sub.get('title', '')}】！"
            ),
            success_keys=found_keys,
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
