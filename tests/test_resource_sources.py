from moviesync.services.resource_sources import ResourceSourceManager


class FakeTelegramClient:
    def search_channel(self, channel, title):
        return [{
            "pwd_id": "abc123",
            "channel": channel["name"],
        }]

    def check_channel_detail(self, channel):
        return {"status": "healthy", "message": "正常"}


class FakeLogger:
    def exception(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass


def test_resource_source_uses_telegram_card_config():
    class Store:
        def load(self):
            return {
                "cards": {
                    "telegram": {
                        "enabled": True,
                        "config": {
                            "channels": [{"id": "movie_channel", "name": "电影频道"}],
                        },
                    }
                }
            }

        def update_resource_source_health(self, *args, **kwargs):
            pass

        def get_resource_sources(self):
            return [{
                "id": "telegram",
                "name": "Telegram",
                "type": "telegram",
                "enabled": True,
                "health": {},
            }]

    manager = ResourceSourceManager(FakeTelegramClient(), Store(), FakeLogger())
    results = manager.search(
        {"title": "测试电影"},
        Store().load(),
    )

    assert len(results) == 1
    assert results[0]["source_id"] == "telegram"
    assert results[0]["channel"] == "电影频道"


def test_resource_source_health_uses_telegram_card_config():
    class Store:
        def load(self):
            return {
                "cards": {
                    "telegram": {
                        "enabled": True,
                        "config": {
                            "channels": [{"id": "movie_channel", "name": "电影频道"}],
                        },
                    }
                }
            }

        def update_resource_source_health(self, *args, **kwargs):
            self.last = args

        def get_resource_sources(self):
            return []

    store = Store()
    manager = ResourceSourceManager(FakeTelegramClient(), store, FakeLogger())
    results = manager.check_all()

    assert results[0]["id"] == "telegram"
    assert results[0]["status"] == "healthy"
    assert results[0]["total"] == 1
    assert results[0]["valid_count"] == 1
