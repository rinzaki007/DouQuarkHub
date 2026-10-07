"""自动追剧订阅管理单元测试。

覆盖：订阅 ID 唯一性、检测周期持久化和首次运行时间生成。
"""
from moviesync.services.subscriptions import SubscriptionManager


def test_subscription_ids_are_unique_and_interval_is_stored(tmp_path):
    manager = SubscriptionManager(tmp_path / "subscriptions.json", lambda: "", __import__("logging").getLogger("test"))
    first = manager.add_subscription(title="A", pwd_id="abc", interval_hours=6)
    second = manager.add_subscription(title="B", pwd_id="def", interval_hours=12)
    assert first["id"] != second["id"]
    assert first["next_run_at"] is not None
    assert manager.get_subscriptions()[1]["interval_hours"] == 12


def test_subscription_failure_uses_retry_backoff(tmp_path):
    import logging

    manager = SubscriptionManager(
        tmp_path / "subscriptions.json",
        lambda: "",
        logging.getLogger("test"),
    )
    sub = manager.add_subscription(
        title="Retry",
        pwd_id="abc",
        interval_hours=6,
    )

    ok, _ = manager._finish(
        sub,
        False,
        "temporary failure",
    )

    assert not ok
    saved = manager.get_subscriptions()[0]
    assert saved["retry_count"] == 1
    assert saved["next_run_at"] < __import__("time").time() + 6 * 3600
    assert saved["last_error"] == "temporary failure"
