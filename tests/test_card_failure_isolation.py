"""卡片故障隔离回归测试。"""

from moviesync.app import create_app
from moviesync.cards import Card, CardManifest


class BrokenStatusCard(Card):
    manifest = CardManifest(
        id="test.broken-status",
        name="状态异常测试卡片",
        type="custom",
    )

    def is_configured(self, config):
        raise RuntimeError("simulated card failure")


def test_broken_card_does_not_break_card_list_or_other_platform_pages(tmp_path):
    app = create_app(
        test_config={"MOVIESYNC_DATA_DIR": str(tmp_path)},
        start_scheduler=False,
    )
    app.config["TESTING"] = True
    services = app.extensions["moviesync"]
    services["card_registry"].register(BrokenStatusCard())
    services["auth"].is_initialized = lambda: True

    client = app.test_client()
    with client.session_transaction() as session:
        session["logged_in"] = True
        session["csrf_token"] = "test-token"
    response = client.get("/api/cards")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert any(card["id"] == "test.broken-status" for card in payload["cards"])
    broken = next(card for card in payload["cards"] if card["id"] == "test.broken-status")
    assert broken["configured"] is False
    assert broken["health"]["status"] == "error"
    assert any("其他卡片仍可使用" in warning for warning in payload["warnings"])

    home = client.get("/")
    assert home.status_code == 200
    services["shutdown"]()
