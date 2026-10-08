from moviesync.clients.telegram import TelegramClient


class FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


class FakeSession:
    def __init__(self):
        self.urls = []

    def get(self, url, timeout):
        self.urls.append(url)
        if "before=100" in url:
            return FakeResponse(
                '<div class="tgme_widget_message" data-post="demo/99">'
                '<div class="tgme_widget_message_text">测试剧 第45集 '
                'https://pan.quark.cn/s/episode45</div></div>'
            )
        return FakeResponse(
            '<div class="tgme_widget_message" data-post="demo/100">'
            '<div class="tgme_widget_message_text">测试剧 第44集 '
            'https://pan.quark.cn/s/episode44</div></div>'
        )


def test_search_channel_crawls_older_messages_for_new_episodes():
    client = TelegramClient()
    session = FakeSession()
    client.http.session = session

    results = client.search_channel({"id": "demo", "name": "测试频道"}, "测试剧")

    assert [item["pwd_id"] for item in results] == ["episode44", "episode45"]
    assert any("before=100" in url for url in session.urls)
