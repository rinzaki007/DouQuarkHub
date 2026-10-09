import pytest

from moviesync.cards import Card, CardManifest, ResourceSourceCard
from moviesync.services import resource_sources as resource_sources_module
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


def test_manager_registers_direct_resource_source_card():
    from moviesync.cards import CardManifest, ResourceSourceCard

    class Store:
        def load(self):
            return {
                "cards": {
                    "telegram": {"enabled": True, "config": {"channels": []}},
                    "sample-source": {"enabled": True, "config": {"prefix": "test"}},
                }
            }

        def update_resource_source_health(self, *args, **kwargs):
            pass

    class DirectCard(ResourceSourceCard):
        manifest = CardManifest(
            id="sample-source",
            name="Sample Source",
            type="resource_source",
            capabilities=("resource.search", "resource.health_check"),
        )

        def search(self, movie, config):
            return [
                {"pwd_id": "sample123", "title": movie["title"] + config["prefix"]},
                None,
            ]

        def check(self, config):
            return {"status": "healthy", "message": "sample ok"}

    manager = ResourceSourceManager(
        FakeTelegramClient(), Store(), FakeLogger(),
        resource_cards=[DirectCard()],
    )
    results = manager.search({"title": "Film"}, Store().load())

    assert any(item["source_id"] == "sample-source" for item in results)
    sample = next(item for item in results if item["source_id"] == "sample-source")
    assert sample["source_name"] == "Sample Source"
    assert sample["title"] == "Filmtest"
    assert manager.check_all()[-1]["id"] == "sample-source"


def test_manager_rejects_non_resource_card_registration():
    class OtherCard(Card):
        pass

    manager = ResourceSourceManager(FakeTelegramClient(), object(), FakeLogger())
    with pytest.raises(TypeError):
        manager.register(OtherCard())


def test_manager_loads_installed_resource_card_entry_points(monkeypatch):
    class PluginCard(ResourceSourceCard):
        manifest = CardManifest(
            id="entrypoint-source",
            name="Entry Point Source",
            type="resource_source",
            capabilities=("resource.search",),
        )

        def search(self, movie, config):
            return []

        def check(self, config):
            return {"status": "healthy", "message": "ok"}

    class FakeEntryPoint:
        name = "entrypoint-source"

        def load(self):
            return lambda context: PluginCard()

    monkeypatch.setattr(resource_sources_module, "entry_points", lambda **kwargs: [FakeEntryPoint()])
    manager = ResourceSourceManager(FakeTelegramClient(), object(), FakeLogger())

    assert manager.load_plugins({"example": True}) == ["entrypoint-source"]
    assert manager.registry.get("entrypoint-source") is not None
