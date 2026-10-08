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
