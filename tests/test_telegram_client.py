"""Regression tests for public Telegram channel parsing and search fallback."""

from moviesync.clients.telegram import TelegramClient


class FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, timeout):
        self.calls.append((url, timeout))
        if self.responses:
            response = self.responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        return FakeResponse(200, "")


def make_client(responses):
    client = TelegramClient()
    session = FakeSession(responses)
    client.http = type("FakeHttp", (), {"session": session})()
    return client, session


def test_search_falls_back_from_empty_query_and_deduplicates_share_links():
    message_html = """
    <div class="tgme_widget_message" data-post="movie_channel/123">
      <div class="tgme_widget_message_text">怪奇物语 S04E01 更新</div>
      <a href="https://pan.quark.cn/s/Abc123">夸克链接</a>
      <a href="https://pan.quark.cn/s/Abc123">重复链接</a>
    </div>
    """
    client, session = make_client([
        FakeResponse(200, "<html><body>empty search</body></html>"),
        FakeResponse(200, message_html),
        FakeResponse(200, ""),
    ])

    results = client.search_channel(
        {"id": "@movie_channel", "name": "影视资源"},
        "怪奇物语",
    )

    assert results == [{
        "channel": "影视资源",
        "channel_id": "movie_channel",
        "pwd_id": "Abc123",
    }]
    assert "?q=" in session.calls[0][0]
    assert session.calls[1][0] == "https://t.me/s/movie_channel"
    assert session.calls[2][0].endswith("?before=123")


def test_search_rejects_invalid_channel_and_ignores_unmatched_titles():
    client, session = make_client([FakeResponse(200, "")])
    assert client.search_channel("https://t.me/not-a-channel", "测试") == []
    assert session.calls == []

    html = """
    <div class="tgme_widget_message" data-post="movie_channel/100">
      <div class="tgme_widget_message_text">另一个节目</div>
      <a href="https://pan.quark.cn/s/ShouldNotMatch">夸克链接</a>
    </div>
    """
    client, session = make_client([FakeResponse(200, html), FakeResponse(200, "")])
    assert client.search_channel("movie_channel", "目标节目") == []
    assert len(session.calls) == 2


def test_channel_health_distinguishes_http_failure_and_public_channel_page():
    client, _ = make_client([FakeResponse(404, "")])
    assert client.check_channel_detail("movie_channel") == {
        "status": "unavailable",
        "message": "频道不存在或无法访问",
    }

    client, _ = make_client([FakeResponse(200, "<html>other page</html>")])
    assert client.check_channel_detail("movie_channel")["status"] == "degraded"

    client, _ = make_client([FakeResponse(200, '<div class="tgme_channel_info"></div>')])
    assert client.check_channel_detail("movie_channel")["status"] == "healthy"


def test_channel_health_does_not_expose_exception_details():
    client, _ = make_client([RuntimeError("cookie=SECRET_VALUE")])
    result = client.check_channel_detail("movie_channel")
    assert result["status"] == "unavailable"
    assert result["message"] == "连接失败：RuntimeError"
    assert "SECRET_VALUE" not in result["message"]
