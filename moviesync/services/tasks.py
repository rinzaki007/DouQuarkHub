"""统一任务中心服务：持久化一次性转存任务与执行历史。"""
from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import RLock

from ..storage import JsonStore


MAX_TASKS = 300


class TaskManager:
    def __init__(self, path, logger):
        self.store = JsonStore(path, lambda: [])
        self.logger = logger
        self.lock = RLock()
        self.executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="moviesync-task")

    def list_tasks(self):
        with self.lock:
            items = self.store.read()
            if not isinstance(items, list):
                return []
            return [dict(item) for item in items if isinstance(item, dict)]

    def _save(self, items):
        self.store.write(items[-MAX_TASKS:])

    def create_transfer_task(self, payload, runner):
        task = {
            "id": uuid.uuid4().hex,
            "type": "transfer",
            "kind": "普通转存",
            "title": str(payload.get("title") or "未命名资源")[:200],
            "status": "queued",
            "progress": 0,
            "total": max(0, len(payload.get("candidate", {}).get("files", []) or [])),
            "success_count": 0,
            "skipped_count": 0,
            "failed_count": 0,
            "message": "等待执行",
            "created_at": time.time(),
            "updated_at": time.time(),
            "retry_payload": payload,
        }
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
            current.update(changes)
            current["updated_at"] = time.time()
            self._save(items)

    def _run_transfer(self, task_id, runner):
        self._update(task_id, status="running", progress=10, message="正在验证资源…")
        try:
            result = runner(lambda progress, message: self._update(
                task_id, progress=max(0, min(100, int(progress))), message=str(message)[:300]
            ))
            ok, message, counts = result
            counts = counts if isinstance(counts, dict) else {}
            self._update(
                task_id,
                status="success" if ok else "failed",
                progress=100 if ok else max(10, self._get(task_id).get("progress", 10)),
                message=str(message)[:500],
                success_count=int(counts.get("success", 0)),
                skipped_count=int(counts.get("skipped", 0)),
                failed_count=int(counts.get("failed", 0)),
            )
        except Exception as exc:
            self.logger.exception("一次性转存任务 %s 执行异常", task_id)
            self._update(task_id, status="failed", message=f"任务执行异常: {exc}", failed_count=1)

    def _get(self, task_id):
        return next((x for x in self.list_tasks() if x.get("id") == task_id), {})

    def get_task(self, task_id):
        return self._get(str(task_id))

    def retry_transfer(self, task_id, runner):
        old = self._get(str(task_id))
        if not old or old.get("type") != "transfer":
            return None
        payload = old.get("retry_payload") or {}
        with self.lock:
            items = self.list_tasks()
            new = dict(old)
            new["id"] = uuid.uuid4().hex
            new["status"] = "queued"
            new["progress"] = 0
            new["message"] = "等待重试"
            new["success_count"] = new["skipped_count"] = new["failed_count"] = 0
            new["created_at"] = time.time()
            new["updated_at"] = time.time()
            items.append(new)
            self._save(items)
        self.executor.submit(self._run_transfer, new["id"], runner)
        return new

    def shutdown(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
