from moviesync.services.resource_sources import ResourceSourceManager


class FakeTelegramClient:
    def __init__(self):
        self.last_scan_all = None

    def search_channel(self, channel, title, scan_all=False):
        self.last_scan_all = scan_all
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



def test_resource_source_parses_episode_using_card_magic_regex():
    class Store:
        def load(self):
            return {
                "cards": {
                    "telegram": {
                        "enabled": True,
                        "config": {
                            "channels": [],
                            "magic_regex": {
                                "pattern": r".*?(?<!\\d)([Ss]\\d{1,2})?([Ee]?[Pp]?[Xx]?\\d{1,3})(?!\\d).*?\\.(mp4|mkv)",
                                "replace": r"\\1\\2.\\3",
                            },
                        },
                    }
                }
            }

        def update_resource_source_health(self, *args, **kwargs):
            pass

        def get_resource_sources(self):
            return []

    manager = ResourceSourceManager(FakeTelegramClient(), Store(), FakeLogger())
    assert manager.parse_tv_episode(
        "telegram",
        "Stranger.Things.S04E01.2022.NF.WEB-DL.2160p.HEVC.HDR.DDP.mkv",
    ) == (4, 1)
    assert manager.parse_tv_episode(
        "telegram",
        "Stranger.Things.S02E09.2160p.BluRay.x265.10bit.DTS.mkv",
    ) == (2, 9)


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



def test_channel_search_scans_recent_messages_without_telegram_title_query():
    class Store:
        def load(self):
            return {
                "cards": {
                    "telegram": {
                        "enabled": True,
                        "config": {"channels": []},
                    }
                }
            }

        def update_resource_source_health(self, *args, **kwargs):
            pass

        def get_resource_sources(self):
            return []

    client = FakeTelegramClient()
    manager = ResourceSourceManager(client, Store(), FakeLogger())

    results = manager.search_channel(
        "telegram",
        {"id": "movie_channel", "name": "电影频道"},
        "测试剧",
    )

    assert len(results) == 1
    assert client.last_scan_all is True
