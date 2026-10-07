"""统一任务中心服务：持久化一次性转存任务与执行历史。"""
from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import RLock

from ..storage import JsonStore

MAX_TASKS = 300
TASK_SCHEMA_VERSION = 2
MAX_EVENTS = 60


class TaskManager:
    def __init__(self, path, logger):
        self.store = JsonStore(path, lambda: [])
        self.logger = logger
        self.lock = RLock()
        self.executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="moviesync-task")
        self._recover_interrupted_tasks()

    def _recover_interrupted_tasks(self):
        with self.lock:
            items = self.store.read()
            if not isinstance(items, list):
                return
            changed = False
            for item in items:
                if not isinstance(item, dict):
                    continue
                if item.get("status") in {"queued", "running"}:
                    item["status"] = "failed"
                    item["phase"] = "failed"
                    item["phase_label"] = "任务中断"
                    item["message"] = "服务重启导致任务中断，可执行失败重试"
                    item["failed_count"] = max(1, int(item.get("failed_count", 0) or 0))
                    item["updated_at"] = time.time()
                    self._append_event(item, "error", item["message"])
                    changed = True
                if item.get("schema_version") != TASK_SCHEMA_VERSION:
                    item["schema_version"] = TASK_SCHEMA_VERSION
                    item.setdefault("phase", "waiting")
                    item.setdefault("phase_label", "等待执行")
                    item.setdefault("events", [])
                    changed = True
            if changed:
                self._save(items)

    def list_tasks(self):
        with self.lock:
            items = self.store.read()
            if not isinstance(items, list):
                return []
            return [dict(item) for item in items if isinstance(item, dict)]

    def _save(self, items):
        self.store.write(items[-MAX_TASKS:])

    @staticmethod
    def _phase_for_progress(progress):
        value = int(progress or 0)
        if value <= 10:
            return "validate", "校验资源"
        if value <= 30:
            return "list_files", "获取文件列表"
        if value <= 60:
            return "create_folder", "准备目标文件夹"
        if value < 100:
            return "transfer", "提交夸克转存"
        return "completed", "转存完成"

    @staticmethod
    def _append_event(item, level, message):
        events = item.setdefault("events", [])
        text = str(message or "").strip()
        if not text:
            return
        if events and events[-1].get("message") == text:
            return
        events.append({
            "at": time.time(),
            "level": str(level or "info"),
            "message": text[:300],
        })
        del events[:-MAX_EVENTS]

    def create_transfer_task(self, payload, runner):
        movie = payload.get("movie") if isinstance(payload.get("movie"), dict) else {}
        title = str(movie.get("title") or movie.get("name") or payload.get("title") or "未命名资源")[:200]
        candidate = payload.get("candidate") if isinstance(payload.get("candidate"), dict) else {}
        files = candidate.get("files") if isinstance(candidate.get("files"), list) else []
        now = time.time()
        task = {
            "id": uuid.uuid4().hex,
            "schema_version": TASK_SCHEMA_VERSION,
            "type": "transfer",
            "kind": "普通转存",
            "title": title,
            "cover": str(movie.get("cover") or ""),
            "status": "queued",
            "phase": "waiting",
            "phase_label": "等待执行",
            "progress": 0,
            "total": max(0, len(files)),
            "success_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "message": "任务已创建，等待执行",
            "source_channel": str(candidate.get("channel") or ""),
            "share_code": str(candidate.get("pwd_id") or ""),
            "target_fid": str(payload.get("target_fid") or "0"),
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "updated_at": now,
            "events": [],
            "retry_payload": payload,
        }
        self._append_event(task, "info", "任务已创建")
        with self.lock:
            items = self.list_tasks()
            items.append(task)
            self._save(items)
        self.executor.submit(self._run_transfer, task["id"], runner)
        return task

    def _update(self, task_id, **changes):
        with self.lock:
            items = self.list_tasks()
            current = next((x for x in items if x.get("id") == task_id), None)
            if not current:
                return
            old_message = current.get("message")
            current.update(changes)
            current["updated_at"] = time.time()
            message = current.get("message")
            if message and message != old_message:
                level = "error" if current.get("status") == "failed" else (
                    "success" if current.get("status") == "success" else "info"
                )
                self._append_event(current, level, message)
            self._save(items)

    def _progress_update(self, task_id, progress, message):
        value = max(0, min(100, int(progress)))
        phase, phase_label = self._phase_for_progress(value)
        self._update(
            task_id,
            progress=value,
            message=str(message)[:300],
            phase=phase,
            phase_label=phase_label,
        )

    def _run_transfer(self, task_id, runner):
        self._update(
            task_id,
            status="running",
            progress=10,
            phase="validate",
            phase_label="校验资源",
            message="正在重新验证分享资源…",
            started_at=time.time(),
        )
        try:
            result = runner(lambda progress, message: self._progress_update(task_id, progress, message))
            ok, message, counts = result
            counts = counts if isinstance(counts, dict) else {}
            now = time.time()
            current = self._get(task_id)
            final_progress = 100 if ok else max(10, int(current.get("progress", 10)))
            self._update(
                task_id,
                status="success" if ok else "failed",
                progress=final_progress,
                phase="completed" if ok else "failed",
                phase_label="转存完成" if ok else "执行失败",
                message=str(message)[:500],
                success_count=int(counts.get("success", 0)),
                skipped_count=int(counts.get("skipped", 0)),
                failed_count=int(counts.get("failed", 0)),
                finished_at=now,
            )
        except Exception as exc:
            self.logger.exception("一次性转存任务 %s 执行异常", task_id)
            self._update(
                task_id,
                status="failed",
                phase="failed",
                phase_label="执行失败",
                message=f"任务执行异常: {exc}",
                failed_count=1,
                finished_at=time.time(),
            )

    def _get(self, task_id):
        return next((x for x in self.list_tasks() if x.get("id") == task_id), {})

    def get_task(self, task_id):
        return self._get(str(task_id))

    def retry_transfer(self, task_id, runner):
        old = self._get(str(task_id))
        if not old or old.get("type") != "transfer":
            return None
        if old.get("status") != "failed":
            return None
        with self.lock:
            items = self.list_tasks()
            new = dict(old)
            new["id"] = uuid.uuid4().hex
            new["status"] = "queued"
            new["phase"] = "waiting"
            new["phase_label"] = "等待重试"
            new["progress"] = 0
            new["message"] = "已创建重试任务，等待执行"
            new["success_count"] = new["skipped_count"] = new["failed_count"] = 0
            new["created_at"] = time.time()
            new["started_at"] = None
            new["finished_at"] = None
            new["updated_at"] = time.time()
            new["events"] = []
            self._append_event(new, "info", "已创建重试任务")
            items.append(new)
            self._save(items)
        self.executor.submit(self._run_transfer, new["id"], runner)
        return new

    def delete_task(self, task_id):
        task_id = str(task_id)
        with self.lock:
            items = self.list_tasks()
            target = next((x for x in items if str(x.get("id")) == task_id), None)
            if not target:
                return False, "任务不存在"
            if target.get("status") in {"queued", "running"}:
                return False, "执行中的任务不能删除，请等待任务结束"
            items = [x for x in items if str(x.get("id")) != task_id]
            self._save(items)
        return True, "任务已删除"

    def clear_history(self):
        with self.lock:
            items = self.list_tasks()
            kept = [x for x in items if x.get("status") in {"queued", "running"}]
            removed = len(items) - len(kept)
            self._save(kept)
        return removed

    def shutdown(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
