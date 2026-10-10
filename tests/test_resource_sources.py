import pytest

from moviesync.cards import Card, CardManifest, ResourceSourceCard
from card_templates.telegram import TelegramResourceSource
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

    manager = ResourceSourceManager(Store(), FakeLogger())
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
    manager = ResourceSourceManager(store, FakeLogger())
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
    manager = ResourceSourceManager(Store(), FakeLogger())

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
        Store(), FakeLogger(),
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

    manager = ResourceSourceManager(object(), FakeLogger())
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


def test_resource_source_health_does_not_expose_plugin_exception():
    class Store:
        def load(self):
            return {
                "cards": {
                    "broken-source": {"enabled": True, "config": {}},
                }
            }

        def update_resource_source_health(self, *args, **kwargs):
            pass

    class BrokenCard(ResourceSourceCard):
        manifest = CardManifest(
            id="broken-source",
            name="Broken Source",
            type="resource_source",
            capabilities=("resource.health_check",),
        )

        def check(self, config):
            raise RuntimeError("upstream cookie=SECRET_COOKIE_VALUE")

    manager = ResourceSourceManager(
        Store(),
        FakeLogger(),
        resource_cards=[BrokenCard()],
    )

    result = next(item for item in manager.check_all() if item["id"] == "broken-source")

    assert result["status"] == "unavailable"
    assert result["message"] == "资源来源连接检查失败，请查看服务日志"
    assert "SECRET_COOKIE_VALUE" not in result["message"]


def test_resource_health_result_cannot_override_card_identity():
    from moviesync.cards import CardManifest, ResourceSourceCard

    class Store:
        def load(self):
            return {
                "cards": {
                    "telegram": {"enabled": True, "config": {}},
                    "identity-source": {"enabled": True, "config": {}},
                }
            }

        def update_resource_source_health(self, *args, **kwargs):
            pass

    class IdentitySpoofCard(ResourceSourceCard):
        manifest = CardManifest(
            id="identity-source",
            name="Identity Source",
            type="resource_source",
            capabilities=("resource.search", "resource.health_check"),
        )

        def search(self, movie, config):
            return []

        def check(self, config):
            return {
                "id": "another-card",
                "name": "Spoofed Name",
                "type": "storage_target",
                "enabled": False,
                "status": "healthy",
                "message": "ok",
            }

    manager = ResourceSourceManager(
        Store(),
        FakeLogger(),
        resource_cards=[IdentitySpoofCard()],
    )

    result = next(item for item in manager.check_all() if item["id"] == "identity-source")

    assert result["name"] == "Identity Source"
    assert result["type"] == "resource_source"
    assert result["enabled"] is True
    assert result["status"] == "healthy"



def test_resource_search_result_cannot_spoof_source_identity():
    class Store:
        def load(self):
            return {"cards": {"telegram": {"enabled": True, "config": {}},
                              "identity-source": {"enabled": True, "config": {}}}}

        def update_resource_source_health(self, *args, **kwargs):
            pass

    class SpoofCard(ResourceSourceCard):
        manifest = CardManifest(
            id="identity-source",
            name="Trusted Source Name",
            type="resource_source",
            capabilities=("resource.search", "resource.health_check"),
        )

        def search(self, movie, config):
            return [{"pwd_id": "abc123", "source_id": "telegram", "source_name": "Impersonated Source"}]

        def check(self, config):
            return {"status": "healthy"}

    manager = ResourceSourceManager(
        FakeTelegramClient(), Store(), FakeLogger(), resource_cards=[SpoofCard()]
    )
    results = manager.search({"title": "Film"}, Store().load())
    item = next(result for result in results if result["pwd_id"] == "abc123")

    assert item["source_id"] == "identity-source"
    assert item["source_name"] == "Trusted Source Name"



def test_resource_source_manager_reflects_registry_unregister():
    from moviesync.cards import CardRegistry

    class Store:
        def load(self):
            return {"cards": {"removable-source": {"enabled": True, "config": {}}}}

        def update_resource_source_health(self, *args, **kwargs):
            pass

        def get_resource_sources(self):
            return []

    class RemovableSource(ResourceSourceCard):
        manifest = CardManifest(
            id="removable-source",
            name="Removable Source",
            type="resource_source",
            capabilities=("resource.search", "resource.health_check"),
        )

        def search(self, movie, config):
            return [{"title": "should not appear"}]

        def check(self, config):
            return {"status": "healthy"}

    registry = CardRegistry()
    manager = ResourceSourceManager(
        FakeTelegramClient(),
        Store(),
        FakeLogger(),
        registry=registry,
    )
    manager.register(RemovableSource())

    assert "removable-source" in manager.sources
    registry.unregister("removable-source")

    assert "removable-source" not in manager.sources
    assert manager.search({"title": "test"}, Store().load()) == []


def test_resource_plugin_factory_closes_card_when_registration_fails(monkeypatch):
    class ExistingCard(ResourceSourceCard):
        manifest = CardManifest(
            id="duplicate-source",
            name="Existing",
            type="resource_source",
            capabilities=("resource.search", "resource.health_check"),
        )

        def search(self, movie, config):
            return []

        def check(self, config):
            return {"status": "healthy"}

    class CandidateCard(ExistingCard):
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    candidate = CandidateCard()

    class EntryPoint:
        name = "duplicate-source-plugin"

        def load(self):
            return lambda context: candidate

    monkeypatch.setattr(
        resource_sources_module, "entry_points", lambda **kwargs: [EntryPoint()]
    )
    registry = __import__("moviesync.cards", fromlist=["CardRegistry"]).CardRegistry()
    registry.register(ExistingCard())
    manager = ResourceSourceManager(
        object(), FakeLogger(), registry=registry
    )

    assert manager.load_plugins() == []
    assert candidate.closed is True
    assert registry.get("duplicate-source") is not candidate


def test_resource_manager_lists_only_resource_source_manifests():
    class OtherCard(Card):
        manifest = CardManifest(
            id="demo-storage-card",
            name="Demo Storage",
            type="storage_target",
            capabilities=("storage.transfer",),
        )

    from moviesync.cards import CardRegistry

    registry = CardRegistry()
    manager = ResourceSourceManager(
        object(), FakeLogger(), registry=registry
    )
    registry.register(OtherCard())

    manifests = manager.get_cards()
    assert [item["id"] for item in manifests] == ["telegram"]
    assert all(item["type"] == "resource_source" for item in manifests)


def test_health_persistence_failure_does_not_stop_other_resource_checks():
    class HealthyCard(ResourceSourceCard):
        def __init__(self, card_id):
            self.manifest = CardManifest(
                id=card_id,
                name=card_id,
                type="resource_source",
                capabilities=("resource.health_check",),
            )

        def search(self, movie, config):
            return []

        def check(self, config):
            return {"status": "healthy", "message": "ok", "total": 1, "valid_count": 1}

    class Store:
        def load(self):
            return {
                "cards": {
                    "health-one": {"enabled": True, "config": {}},
                    "health-two": {"enabled": True, "config": {}},
                }
            }

        def update_resource_source_health(self, *args, **kwargs):
            raise RuntimeError("health persistence unavailable")

    manager = ResourceSourceManager(
        Store(),
        FakeLogger(),
        resource_cards=[HealthyCard("health-one"), HealthyCard("health-two")],
    )

    results = manager.check_all()
    assert [item["id"] for item in results if item["id"].startswith("health-")] == [
        "health-one",
        "health-two",
    ]
    assert all(item["status"] == "healthy" for item in results if item["id"].startswith("health-"))
