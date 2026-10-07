from moviesync.services.subscriptions import SubscriptionManager


def test_subscription_ids_are_unique_and_interval_is_stored(tmp_path):
    manager = SubscriptionManager(tmp_path / "subscriptions.json", lambda: "", __import__("logging").getLogger("test"))
    first = manager.add_subscription(title="A", pwd_id="abc", interval_hours=6)
    second = manager.add_subscription(title="B", pwd_id="def", interval_hours=12)
    assert first["id"] != second["id"]
    assert first["next_run_at"] is not None
    assert manager.get_subscriptions()[1]["interval_hours"] == 12
