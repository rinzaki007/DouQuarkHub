"""任务中心与自动追剧状态回归测试。"""

import logging

from moviesync.services.subscriptions import SubscriptionManager
from moviesync.services.tasks import TaskManager


def test_transfer_retry_only_accepts_failed_task(tmp_path):
    manager = TaskManager(tmp_path / "tasks.json", logging.getLogger("test"))
    failed = {
        "id": "failed-task",
        "type": "transfer",
        "status": "failed",
        "title": "测试电影",
        "events": [],
        "retry_payload": {"movie": {"title": "测试电影"}, "candidate": {"files": []}},
    }
    queued = dict(failed, id="queued-task", status="queued")
    manager.store.write([queued, failed])

    assert manager.retry_transfer(queued["id"], lambda progress: None) is None
    retry = manager.retry_transfer(failed["id"], lambda progress: (True, "ok", {"success": 0}))
    assert retry is not None
    assert retry["status"] == "queued"
    manager.shutdown()


def test_subscription_success_clears_pending_save_keys(tmp_path):
    manager = SubscriptionManager(
        tmp_path / "subscriptions.json",
        lambda: "cookie",
        logging.getLogger("test"),
    )
    sub = manager.add_subscription(
        title="测试追剧",
        pwd_id="abc123",
        files=[{"fid": "file1"}],
    )

    with manager.lock:
        items = manager._load_subscriptions()
        items[0]["pending_save_keys"] = ["file1"]
        manager.store.write(items)

    ok, _ = manager._finish(
        sub,
        True,
        "转存成功",
        success_keys=["file1"],
    )

    assert ok is True
    current = manager.get_subscriptions()[0]
    assert current["pending_save_keys"] == []
    assert "file1" in current["saved_episodes"]


def test_running_subscription_cannot_be_deleted(tmp_path):
    manager = SubscriptionManager(
        tmp_path / "subscriptions.json",
        lambda: "cookie",
        logging.getLogger("test"),
    )
    sub = manager.add_subscription(title="测试追剧", pwd_id="abc123")

    with manager.lock:
        manager.running_ids.add(sub["id"])

    assert manager.delete_subscription(sub["id"]) is False
    assert manager.get_subscriptions()



def test_duplicate_transfer_submission_reuses_active_task(tmp_path):
    from threading import Event

    manager = TaskManager(tmp_path / "tasks.json", logging.getLogger("test"))
    started = Event()
    release = Event()
    calls = []
    payload = {
        "movie": {"title": "同一部电影"},
        "candidate": {"pwd_id": "share-1", "files": [{"fid": "file-1"}]},
        "target_fid": "target-1",
    }

    def runner(progress):
        calls.append(1)
        started.set()
        assert release.wait(3)
        return True, "ok", {"success": 1, "skipped": 0, "failed": 0}

    try:
        first = manager.create_transfer_task(payload, runner)
        assert started.wait(2)
        second = manager.create_transfer_task(payload, runner)
        assert second["id"] == first["id"]
        assert len(manager.list_tasks()) == 1
        assert len(calls) == 1
    finally:
        release.set()
        manager.executor.shutdown(wait=True)


def test_duplicate_retry_reuses_existing_active_retry(tmp_path):
    from threading import Event

    manager = TaskManager(tmp_path / "tasks.json", logging.getLogger("test"))
    started = Event()
    release = Event()
    payload = {"movie": {"title": "重试电影"}, "candidate": {"pwd_id": "share-2", "files": []}}
    manager.store.write([{
        "id": "failed-task",
        "type": "transfer",
        "status": "failed",
        "title": "重试电影",
        "events": [],
        "retry_payload": payload,
    }])

    def runner(progress):
        started.set()
        assert release.wait(3)
        return True, "ok", {"success": 0}

    try:
        first = manager.retry_transfer("failed-task", runner)
        assert first is not None
        assert started.wait(2)
        second = manager.retry_transfer("failed-task", runner)
        assert second is not None
        assert second["id"] == first["id"]
        assert len(manager.list_tasks()) == 2
    finally:
        release.set()
        manager.executor.shutdown(wait=True)


def test_restart_recovery_only_allows_retry_when_task_never_started(tmp_path):
    import json

    path = tmp_path / "tasks.json"
    payload = {
        "movie": {"title": "恢复测试"},
        "candidate": {"pwd_id": "share-1", "files": [{"fid": "file-1"}]},
        "target_fid": "target-1",
    }
    path.write_text(
        json.dumps([
            {
                "id": "queued-before-restart",
                "type": "transfer",
                "status": "queued",
                "title": "排队任务",
                "events": [],
                "retry_payload": payload,
            },
            {
                "id": "running-before-restart",
                "type": "transfer",
                "status": "running",
                "title": "执行中任务",
                "events": [],
                "retry_payload": payload,
            },
        ]),
        encoding="utf-8",
    )

    manager = TaskManager(path, logging.getLogger("test"))
    try:
        recovered = {task["id"]: task for task in manager.list_tasks()}
        assert recovered["queued-before-restart"]["status"] == "failed"
        assert recovered["queued-before-restart"]["recovery_uncertain"] is False
        assert recovered["running-before-restart"]["status"] == "failed"
        assert recovered["running-before-restart"]["recovery_uncertain"] is True
        assert "检查目标网盘" in recovered["running-before-restart"]["message"]

        assert manager.retry_transfer(
            "running-before-restart",
            lambda progress: (True, "不应执行", {"success": 1}),
        ) is None

        retry = manager.retry_transfer(
            "queued-before-restart",
            lambda progress: (True, "安全重试成功", {"success": 1}),
        )
        assert retry is not None
        assert retry["status"] == "queued"
        manager.executor.shutdown(wait=True)
        assert manager.get_task(retry["id"])["status"] == "success"
    finally:
        manager.shutdown()


def test_uncertain_transfer_failure_disables_direct_retry(tmp_path):
    manager = TaskManager(tmp_path / "tasks.json", logging.getLogger("test"))
    payload = {"movie": {"title": "不确定结果"}, "candidate": {"pwd_id": "share", "files": [{"fid": "f1"}]}}
    try:
        task = manager.create_transfer_task(
            payload,
            lambda progress: (
                False,
                "转存结果不确定：请求可能已到达网盘",
                {"success": 0, "skipped": 0, "failed": 1, "uncertain": True},
            ),
        )
        manager.executor.shutdown(wait=True)
        failed = manager.get_task(task["id"])
        assert failed["status"] == "failed"
        assert failed["recovery_uncertain"] is True
        assert failed["phase_label"] == "结果待核实"
        assert manager.retry_transfer(task["id"], lambda progress: (True, "不应重试", {"success": 1})) is None
    finally:
        manager.shutdown()


def test_deleted_queued_task_never_starts_remote_runner(tmp_path):
    manager = TaskManager(tmp_path / "tasks.json", logging.getLogger("test"))
    calls = []
    try:
        manager.executor.shutdown(wait=True)
        manager.store.write([{
            "id": "queued-task",
            "type": "transfer",
            "status": "queued",
            "title": "待执行任务",
            "events": [],
        }])

        ok, message = manager.delete_task("queued-task")
        assert ok is True
        manager._run_transfer("queued-task", lambda progress: calls.append("ran"))

        assert calls == []
        assert manager.get_task("queued-task") == {}
    finally:
        manager.shutdown()


def test_late_progress_cannot_overwrite_terminal_task_state(tmp_path):
    manager = TaskManager(tmp_path / "tasks.json", logging.getLogger("test"))
    try:
        manager.store.write([{
            "id": "done-task",
            "type": "transfer",
            "status": "success",
            "phase": "completed",
            "phase_label": "转存完成",
            "progress": 100,
            "message": "ok",
            "events": [],
        }])

        manager._progress_update("done-task", 45, "迟到的进度事件")

        current = manager.get_task("done-task")
        assert current["status"] == "success"
        assert current["phase"] == "completed"
        assert current["phase_label"] == "转存完成"
        assert current["progress"] == 100
        assert current["message"] == "ok"
    finally:
        manager.shutdown()


def test_task_history_limit_never_discards_active_tasks(tmp_path):
    manager = TaskManager(tmp_path / "tasks.json", logging.getLogger("test"))
    try:
        items = [
            {"id": f"terminal-{index}", "status": "success"}
            for index in range(305)
        ]
        items.extend([
            {"id": f"active-{index}", "status": "running"}
            for index in range(3)
        ])
        manager._save(items)

        saved = manager.list_tasks()
        saved_ids = {item["id"] for item in saved}
        assert {"active-0", "active-1", "active-2"} <= saved_ids
        assert len(saved) == 300
        assert "terminal-0" not in saved_ids
        assert "terminal-304" in saved_ids
    finally:
        manager.shutdown()


def test_executor_submit_failure_is_recorded_and_retry_remains_safe(tmp_path):
    manager = TaskManager(tmp_path / "tasks.json", logging.getLogger("test"))
    calls = []
    payload = {
        "movie": {"title": "执行器关闭测试"},
        "candidate": {"pwd_id": "share-submit-failure", "files": [{"fid": "file-1"}]},
        "target_fid": "target-1",
    }

    def runner(progress):
        calls.append("ran")
        return True, "ok", {"success": 1}

    try:
        manager.shutdown()

        task = manager.create_transfer_task(payload, runner)
        assert task["status"] == "failed"
        assert task["recovery_uncertain"] is False
        assert "尚未开始转存" in task["message"]
        assert calls == []

        retry = manager.retry_transfer(task["id"], runner)
        assert retry is not None
        assert retry["status"] == "failed"
        assert retry["recovery_uncertain"] is False
        assert "尚未开始转存" in retry["message"]
        assert calls == []
        assert len(manager.list_tasks()) == 2
    finally:
        manager.shutdown()
