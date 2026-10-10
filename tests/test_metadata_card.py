from card_templates.douban import DoubanMetadataCard
from moviesync.cards import MetadataProviderCard


class FakeDouban:
    def get_movies(self, tag, sort_type):
        return [{"title": tag, "sort": sort_type}]

    def search(self, query):
        return [{"title": query}]


def test_douban_metadata_card_uses_standard_interface():
    card = DoubanMetadataCard(FakeDouban())

    assert isinstance(card, MetadataProviderCard)
    assert card.card_id == "douban"
    assert "metadata.list" in card.capabilities
    assert card.list_movies("电影", "U") == [{"title": "电影", "sort": "U"}]
    assert card.search("测试") == [{"title": "测试"}]
    assert card.get_detail("123") is None


def test_metadata_manager_falls_back_when_one_card_raises_or_returns_empty():
    import logging

    from moviesync.cards import CardManifest, CardRegistry, MetadataProviderCard
    from moviesync.services.metadata import MetadataProviderManager

    class BrokenProvider(MetadataProviderCard):
        manifest = CardManifest(
            id="broken-provider",
            name="Broken",
            type="metadata_provider",
            capabilities=("metadata.list", "metadata.search"),
        )

        def list_movies(self, tag, sort_type):
            raise RuntimeError("upstream unavailable")

        def search(self, query):
            return []

        def get_detail(self, item_id):
            return None

    class HealthyProvider(MetadataProviderCard):
        manifest = CardManifest(
            id="healthy-provider",
            name="Healthy",
            type="metadata_provider",
            capabilities=("metadata.list", "metadata.search", "metadata.detail"),
        )

        def list_movies(self, tag, sort_type):
            return [{"title": "healthy"}]

        def search(self, query):
            return [{"title": query}]

        def get_detail(self, item_id):
            return {"id": item_id}

    registry = CardRegistry()
    registry.register(BrokenProvider())
    registry.register(HealthyProvider())
    manager = MetadataProviderManager(registry, logging.getLogger("test.metadata"))

    assert manager.list_movies() == [{"title": "healthy"}]
    assert manager.search("测试") == [{"title": "测试"}]
    assert manager.get_detail("123") == {"id": "123"}


def test_metadata_manager_keeps_explicit_provider_selection_and_validates_results():
    import logging

    from moviesync.cards import CardManifest, CardRegistry, MetadataProviderCard
    from moviesync.services.metadata import MetadataProviderManager

    class MalformedProvider(MetadataProviderCard):
        manifest = CardManifest(
            id="malformed-provider",
            name="Malformed",
            type="metadata_provider",
            capabilities=("metadata.list", "metadata.search", "metadata.detail"),
        )

        def list_movies(self, tag, sort_type):
            return {"title": "not-a-list"}

        def search(self, query):
            raise RuntimeError("secret cookie")

        def get_detail(self, item_id):
            return ["not", "a", "detail"]

    class HealthyProvider(MetadataProviderCard):
        manifest = CardManifest(
            id="healthy-provider",
            name="Healthy",
            type="metadata_provider",
            capabilities=("metadata.list", "metadata.search", "metadata.detail"),
        )

        def list_movies(self, tag, sort_type):
            return [{"title": "healthy"}]

        def search(self, query):
            return [{"title": query}]

        def get_detail(self, item_id):
            return {"id": item_id}

    registry = CardRegistry()
    registry.register(MalformedProvider())
    registry.register(HealthyProvider())
    manager = MetadataProviderManager(registry, logging.getLogger("test.metadata"))

    # An explicitly selected provider is authoritative: never silently swap providers.
    assert manager.list_movies(provider_id="malformed-provider") == []
    assert manager.search("测试", provider_id="malformed-provider") == []
    assert manager.get_detail("123", provider_id="malformed-provider") is None

    # Without explicit selection, invalid result contracts are isolated and fallback works.
    assert manager.list_movies() == [{"title": "healthy"}]
    assert manager.search("测试") == [{"title": "测试"}]
    assert manager.get_detail("123") == {"id": "123"}


def test_metadata_manager_respects_card_capabilities():
    import logging

    from moviesync.cards import CardManifest, CardRegistry, MetadataProviderCard
    from moviesync.services.metadata import MetadataProviderManager

    class ListOnlyProvider(MetadataProviderCard):
        manifest = CardManifest(
            id="list-only-provider",
            name="List Only",
            type="metadata_provider",
            capabilities=("metadata.list",),
        )

        def list_movies(self, tag, sort_type):
            return [{"title": tag}]

        def search(self, query):
            raise AssertionError("unsupported capability must not be called")

        def get_detail(self, item_id):
            raise AssertionError("unsupported capability must not be called")

    registry = CardRegistry()
    registry.register(ListOnlyProvider())
    manager = MetadataProviderManager(registry, logging.getLogger("test.metadata"))

    assert manager.list_movies() == [{"title": "电影"}]
    assert manager.search("测试") == []
    assert manager.get_detail("123") is None


def test_metadata_manager_loads_installed_card_plugins_and_isolates_failures(monkeypatch):
    import logging

    from moviesync.cards import CardManifest, CardRegistry, MetadataProviderCard
    from moviesync.services import metadata as metadata_module
    from moviesync.services.metadata import MetadataProviderManager

    received_context = {}

    class PluginProvider(MetadataProviderCard):
        manifest = CardManifest(
            id="plugin-metadata",
            name="Plugin Metadata",
            type="metadata_provider",
            capabilities=("metadata.list", "metadata.search"),
        )

        def list_movies(self, tag, sort_type):
            return [{"title": "plugin"}]

        def search(self, query):
            return [{"title": query}]

        def get_detail(self, item_id):
            return None

    class EntryPoint:
        def __init__(self, name, factory):
            self.name = name
            self.factory = factory

        def load(self):
            return self.factory

    def factory(context):
        received_context.update(context)
        return PluginProvider()

    monkeypatch.setattr(
        metadata_module,
        "entry_points",
        lambda group: (
            [
                EntryPoint("good-provider", factory),
                EntryPoint("bad-provider", lambda context: object()),
            ]
            if group == "moviesync.metadata_providers"
            else [],
        )[0],
    )

    registry = CardRegistry()
    manager = MetadataProviderManager(registry, logging.getLogger("test.metadata.plugins"))
    context = {"config_store": object(), "logger": logging.getLogger("plugin")}
    assert manager.load_plugins(context) == ["plugin-metadata"]
    assert registry.get("plugin-metadata").card_id == "plugin-metadata"
    assert received_context == context
    assert manager.list_movies() == [{"title": "plugin"}]


def test_metadata_plugin_factory_closes_card_when_registration_fails(monkeypatch):
    import logging

    from moviesync.cards import CardManifest, CardRegistry, MetadataProviderCard
    from moviesync.services import metadata as module
    from moviesync.services.metadata import MetadataProviderManager

    class ExistingProvider(MetadataProviderCard):
        manifest = CardManifest(
            id="duplicate-provider",
            name="Existing",
            type="metadata_provider",
            capabilities=("metadata.list", "metadata.search", "metadata.detail"),
        )

        def list_movies(self, tag, sort_type):
            return []

        def search(self, query):
            return []

        def get_detail(self, item_id):
            return None

    class CandidateProvider(ExistingProvider):
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    candidate = CandidateProvider()

    class EntryPoint:
        name = "duplicate-provider-plugin"

        def load(self):
            return lambda context: candidate

    monkeypatch.setattr(module, "entry_points", lambda group: [EntryPoint()])
    registry = CardRegistry()
    registry.register(ExistingProvider())
    manager = MetadataProviderManager(registry, logging.getLogger("test.metadata.cleanup"))

    assert manager.load_plugins() == []
    assert candidate.closed is True
    assert registry.get("duplicate-provider") is not candidate
