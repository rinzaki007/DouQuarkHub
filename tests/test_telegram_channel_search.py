from card_templates.telegram import TelegramResourceSource


class FakeTelegramClient:
    def __init__(self):
        self.scan_all = None
        self.channel = None
        self.title = None

    def search_channel(self, channel, title, scan_all=False):
        self.channel = channel
        self.title = title
        self.scan_all = scan_all
        return [{"pwd_id": "share123"}]


def test_channel_subscription_uses_telegram_title_search():
    client = FakeTelegramClient()
    source = TelegramResourceSource(client)

    results = source.search_channel(
        {"id": "movie_channel", "name": "影视资源频道"},
        "怪奇物语",
        {},
    )

    assert results == [{"pwd_id": "share123"}]
    assert client.title == "怪奇物语"
    # Automatic tracking scans recent channel messages first so that posts
    # omitted by Telegram's server-side title query can still be matched.
    assert client.scan_all is True
