"""任务中心与自动追剧状态回归测试。"""

from moviesync.services.subscriptions import SubscriptionManager
from moviesync.services.tasks import TaskManager


def test_transfer_retry_only_accepts_failed_task(tmp_path):
    manager = TaskManager(tmp_path / "tasks.json", __import__("logging").getLogger("test"))

    payload = {
        "movie": {"title": "测试电影"},
        "candidate": {"files": [{"fid": "f1"}]},
    }

    queued = manager.create_transfer_task(payload, lambda progress: (True, "ok", {"success": 1}))
    assert manager.retry_transfer(queued["id"], lambda progress: None) is None

    failed = manager._get(queued["id"])
    failed["status"] = "failed"
    with manager.lock:
        manager.store.write([failed])

    retry = manager.retry_transfer(failed["id"], lambda progress: None)
    assert retry is not None
    assert retry["status"] == "queued"
    manager.shutdown()


def test_subscription_success_clears_pending_save_keys(tmp_path):
    manager = SubscriptionManager(
        tmp_path / "subscriptions.json",
        lambda: "cookie",
        __import__("logging").getLogger("test"),
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
        __import__("logging").getLogger("test"),
    )
    sub = manager.add_subscription(title="测试追剧", pwd_id="abc123")

    with manager.lock:
        manager.running_ids.add(sub["id"])

    assert manager.delete_subscription(sub["id"]) is False
    assert manager.get_subscriptions()
