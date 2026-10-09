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
