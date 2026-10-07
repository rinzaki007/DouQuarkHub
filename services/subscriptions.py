from __future__ import annotations

import time
import uuid
from datetime import datetime
from threading import Event, RLock, Thread
from typing import Callable

from ..clients.quark import QuarkClient, clean_tv_filename
from ..storage import JsonStore


class SubscriptionManager:
    def __init__(self, subscriptions_file, get_cookie: Callable[[], str], logger, max_interval_hours: int = 168):
        self.store = JsonStore(subscriptions_file, lambda: [])
        self.get_cookie = get_cookie
        self.logger = logger
        self.max_interval_hours = max_interval_hours
        self.lock = RLock()
        self.running_ids: set[str] = set()
        self.stop_event = Event()
        self.worker: Thread | None = None

    @staticmethod
    def _now_string() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    def get_subscriptions(self) -> list[dict]:
        with self.lock:
            return list(self.store.read())

    def add_subscription(self, *, title: str, pwd_id: str, target_fid: str = "0", interval_hours: int = 6, start_ep: int = 0, channel: str = "", files=None) -> dict:
        title = str(title or "").strip()
        pwd_id = str(pwd_id or "").strip()
        if not title or not pwd_id:
            raise ValueError("标题和分享 ID 不能为空")
        interval_hours = int(interval_hours)
        start_ep = max(0, int(start_ep))
        if not 1 <= interval_hours <= self.max_interval_hours:
            raise ValueError(f"检测周期必须在 1-{self.max_interval_hours} 小时之间")

        target_fids = []
        seen = set()
        for item in files or []:
            fid = str(item.get("fid") if isinstance(item, dict) else item or "").strip()
            if fid and fid not in seen:
                seen.add(fid)
                target_fids.append(fid)

        subscription = {
            "id": uuid.uuid4().hex,
            "title": title,
            "pwd_id": pwd_id,
            "target_fid": target_fid or "0",
            "interval_hours": interval_hours,
            "start_ep": start_ep,
            "channel": str(channel or "").strip(),
            "files": [{"fid": fid} for fid in target_fids],
            "saved_episodes": [],
            "last_check": "从未检测",
            "last_check_at": None,
            "next_run_at": time.time(),
            "last_error": "",
        }
        with self.lock:
            subscriptions = self.store.read()
            subscriptions.append(subscription)
            self.store.write(subscriptions)
        return subscription

    def delete_subscription(self, sub_id: str) -> bool:
        with self.lock:
            subscriptions = self.store.read()
            new_subscriptions = [item for item in subscriptions if item.get("id") != str(sub_id)]
            changed = len(new_subscriptions) != len(subscriptions)
            if changed:
                self.store.write(new_subscriptions)
            return changed

    def check_subscription_now(self, sub_id: str) -> tuple[bool, str]:
        with self.lock:
            subscriptions = self.store.read()
            subscription = next((item for item in subscriptions if item.get("id") == str(sub_id)), None)
        if not subscription:
            return False, "未找到订阅任务"

        sub_id = str(sub_id)
        with self.lock:
            if sub_id in self.running_ids:
                return False, "该订阅正在执行，请稍后再试"
            self.running_ids.add(sub_id)
        try:
            return self._check(subscription)
        except Exception as exc:
            self.logger.exception("订阅任务 %s 执行异常", sub_id)
            return self._finish(subscription, False, f"任务执行异常: {exc}")
        finally:
            with self.lock:
                self.running_ids.discard(sub_id)

    def _check(self, sub: dict) -> tuple[bool, str]:
        cookie = self.get_cookie().strip()
        if not cookie:
            return self._finish(sub, False, "缺少夸克 Cookie")

        engine = QuarkClient(cookie)
        files, fetched_stoken, err = engine.get_share_files(sub.get("pwd_id"))
        if err or not files or not fetched_stoken:
            return self._finish(sub, False, f"解析链接失败: {err or '未找到文件'}")

        saved = set(sub.get("saved_episodes", []))
        selected = []
        found_keys = []
        target_files = sub.get("files") or []

        if target_files:
            target_fids = {str(item.get("fid")) for item in target_files if isinstance(item, dict) and item.get("fid")}
            for item in files:
                fid = str(item.get("fid") or "")
                if fid in target_fids and fid not in saved:
                    selected.append({"fid": fid})
                    found_keys.append(fid)
        else:
            start_ep = int(sub.get("start_ep", 0) or 0)
            for item in files:
                ep_num, _ = clean_tv_filename(str(item.get("file_name", "")), str(sub.get("title", "")))
                if ep_num is not None and ep_num > start_ep and ep_num not in saved:
                    selected.append({"fid": item.get("fid")})
                    found_keys.append(ep_num)

        if not selected:
            return self._finish(sub, True, f"《{sub.get('title', '')}》暂无新更新", success_keys=[])

        folder_fid, folder_err = engine.get_or_create_subfolder(str(sub.get("title", "")), str(sub.get("target_fid") or "0"))
        if not folder_fid:
            return self._finish(sub, False, f"创建专属文件夹失败: {folder_err or '未知错误'}")

        ok, msg = engine.save_files(sub.get("pwd_id"), selected, fetched_stoken, folder_fid)
        if not ok:
            return self._finish(sub, False, f"转存失败: {msg}")

        return self._finish(
            sub,
            True,
            f"🎉 成功追更 {len(found_keys)} 项，已存入专属文件夹【{sub.get('title', '')}】！",
            success_keys=found_keys,
        )

    def _finish(self, sub: dict, success: bool, message: str, success_keys=None) -> tuple[bool, str]:
        success_keys = success_keys or []
        with self.lock:
            subscriptions = self.store.read()
            current = next((item for item in subscriptions if item.get("id") == sub.get("id")), None)
            if current is None:
                return success, message
            current["last_check"] = self._now_string() + (" (成功)" if success else " (失败)")
            current["last_check_at"] = time.time()
            current["next_run_at"] = time.time() + int(current.get("interval_hours", 6)) * 3600
            current["last_error"] = "" if success else message
            if success_keys:
                old = list(current.get("saved_episodes", []))
                seen = set(old)
                old.extend(key for key in success_keys if key not in seen)
                current["saved_episodes"] = sorted(old, key=lambda value: (isinstance(value, str), str(value)))
            self.store.write(subscriptions)
        if success:
            self.logger.info(message)
        else:
            self.logger.warning(message)
        return success, message

    def start_scheduler(self) -> None:
        with self.lock:
            if self.worker and self.worker.is_alive():
                return
            self.stop_event.clear()
            self.worker = Thread(target=self._scheduler_loop, name="moviesync-scheduler", daemon=True)
            self.worker.start()
        self.logger.info("自动追剧调度器已启动")

    def stop_scheduler(self) -> None:
        self.stop_event.set()
        worker = self.worker
        if worker and worker.is_alive():
            worker.join(timeout=2)
        self.worker = None

    def _scheduler_loop(self) -> None:
        while not self.stop_event.wait(30):
            now = time.time()
            for sub in self.get_subscriptions():
                if float(sub.get("next_run_at") or 0) > now:
                    continue
                self.check_subscription_now(str(sub.get("id")))
