from moviesync.cards import CardManifest, CardRegistry, StorageTargetCard
from moviesync.services.storage_targets import StorageTargetManager


class FakeStore:
    def load(self):
        return {
            "cards": {
                "demo-storage": {"enabled": True, "config": {}},
                "disabled-storage": {"enabled": False, "config": {}},
            }
        }


class FakeLogger:
    def exception(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass


class DemoStorage(StorageTargetCard):
    manifest = CardManifest(
        id="demo-storage",
        name="Demo Storage",
        type="storage_target",
        capabilities=(
            "storage.check",
            "storage.resolve_resource",
            "storage.list_files",
            "storage.create_folder",
            "storage.transfer",
        ),
    )

    def resolve_resource(self, resource):
        return {
            "files": [{"fid": "1"}],
            "token": "demo-token",
            "error": None,
        }

    def list_files(self, resource):
        return [{"fid": "1"}]

    def create_folder(self, name, parent_id="0"):
        return "folder-1"

    def transfer(self, resource, files, target_id="0"):
        return True, "ok"


class DisabledStorage(DemoStorage):
    manifest = CardManifest(
        id="disabled-storage",
        name="Disabled Storage",
        type="storage_target",
        capabilities=DemoStorage.manifest.capabilities,
    )


def test_storage_target_manager_discovers_enabled_cards():
    registry = CardRegistry()
    registry.register(DemoStorage())
    registry.register(DisabledStorage())
    manager = StorageTargetManager(registry, FakeStore(), FakeLogger())

    assert [item["id"] for item in manager.list_targets()] == [
        "demo-storage",
        "disabled-storage",
    ]
    assert manager.get().card_id == "demo-storage"
    assert manager.get("disabled-storage") is None


def test_storage_target_manager_routes_resource_and_transfer():
    registry = CardRegistry()
    registry.register(DemoStorage())
    manager = StorageTargetManager(registry, FakeStore(), FakeLogger())

    resolved = manager.resolve_resource({"pwd_id": "abc"})
    assert resolved["target_id"] == "demo-storage"
    assert resolved["token"] == "demo-token"

    assert manager.create_folder("Show") == "folder-1"
    ok, message = manager.transfer(
        {"pwd_id": "abc"},
        [{"fid": "1"}],
        "folder-1",
        "demo-storage",
        "demo-token",
    )
    assert ok is True
    assert message == "ok"


def test_storage_target_destination_options():
    from moviesync.cards import StorageTargetCard

    class DestinationCard(StorageTargetCard):
        card_id = "demo"

        def destination_options(self):
            return [{"id": "root", "name": "默认目录", "is_default": True}]

    from moviesync.services.storage_targets import StorageTargetManager

    class Registry:
        def get(self, target_id):
            return DestinationCard() if target_id == "demo" else None

        def find_by_type(self, card_type):
            return [DestinationCard()] if card_type == "storage_target" else []

    class Config:
        def load(self):
            return {"cards": {"demo": {"enabled": True}}}

        def get_default_storage_target_id(self):
            return "demo"

    manager = StorageTargetManager(Registry(), Config(), None)
    assert manager.destination_options("demo") == [{"id": "root", "name": "默认目录", "is_default": True}]



def test_storage_target_manager_loads_installed_plugins(monkeypatch):
    from moviesync.services import storage_targets as module

    received_context = {}

    class EntryPoint:
        name = "external-storage"

        def load(self):
            def factory(context):
                received_context.update(context)
                return DemoStorage()

            return factory

    monkeypatch.setattr(module, "entry_points", lambda group: [EntryPoint()])
    registry = CardRegistry()
    store = FakeStore()
    logger = FakeLogger()
    manager = StorageTargetManager(registry, store, logger)

    assert manager.load_plugins({"config_store": store, "logger": logger}) == ["demo-storage"]
    assert manager.get("demo-storage").card_id == "demo-storage"
    assert received_context == {"config_store": store, "logger": logger}


def test_storage_target_manager_isolates_invalid_plugin(monkeypatch):
    from moviesync.services import storage_targets as module

    class EntryPoint:
        name = "invalid-storage"

        def load(self):
            return lambda context: object()

    monkeypatch.setattr(module, "entry_points", lambda group: [EntryPoint()])
    registry = CardRegistry()
    manager = StorageTargetManager(registry, FakeStore(), FakeLogger())

    assert manager.load_plugins() == []
    assert registry.list() == []
