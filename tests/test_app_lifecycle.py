"""应用生命周期清理回归测试。"""

import logging

from moviesync import app as app_module
from moviesync.cards import CardRegistry


def test_application_shutdown_stops_scheduler_and_closes_cards_once(tmp_path, monkeypatch):
    calls = []

    class FakeSubscriptions:
        def __init__(self, *args, **kwargs):
            pass

        def stop_scheduler(self):
            calls.append("scheduler")

    monkeypatch.setattr(app_module, "SubscriptionManager", FakeSubscriptions)
    monkeypatch.setattr(CardRegistry, "close_all", lambda self: calls.append("cards"))
    monkeypatch.setattr(app_module, "configure_logging", lambda path: logging.getLogger("test.app"))

    app = app_module.create_app(
        test_config={"MOVIESYNC_DATA_DIR": str(tmp_path)},
        start_scheduler=False,
    )
    shutdown = app.extensions["moviesync"]["shutdown"]

    shutdown()
    shutdown()

    assert calls == ["scheduler", "cards"]
