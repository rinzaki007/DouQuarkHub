from moviesync.cards import CardRegistry
from moviesync.cards_metadata import DoubanMetadataCard
from moviesync.services.resource_sources import TelegramResourceSource


def test_card_management_uses_registry_manifests():
    registry = CardRegistry()
    registry.register(DoubanMetadataCard(object()))
    registry.register(TelegramResourceSource(object()))

    cards = registry.manifests()

    assert {item["id"] for item in cards} == {"douban", "telegram"}
    assert {item["type"] for item in cards} == {"metadata_provider", "resource_source"}


def test_generic_resource_card_config_api_sanitizes_secrets_and_saves(tmp_path):
    from moviesync.app import create_app
    from moviesync.cards import CardManifest, ResourceSourceCard

    app = create_app({"MOVIESYNC_DATA_DIR": str(tmp_path)}, start_scheduler=False)
    services = app.extensions["moviesync"]

    class ConfigurableCard(ResourceSourceCard):
        manifest = CardManifest(
            id="configurable-source",
            name="Configurable Source",
            type="resource_source",
            capabilities=("resource.search", "resource.health_check"),
            config_fields=(
                {"key": "endpoint", "label": "Endpoint", "type": "string"},
                {"key": "api_token", "label": "API Token", "type": "password", "secret": True},
            ),
        )

        def search(self, movie, config):
            return []

        def check(self, config):
            return {"status": "healthy", "message": "ok"}

    services["resource_sources"].register(ConfigurableCard())
    client = app.test_client()
    client.post("/api/setup", json={"username": "admin", "password": "password123"})
    with client.session_transaction() as session:
        csrf = session["csrf_token"]

    response = client.post(
        "/api/cards/configurable-source/config",
        json={"enabled": True, "config": {"endpoint": "https://example.test", "api_token": "do-not-leak"}},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["config"]["endpoint"] == "https://example.test"
    assert body["config"]["api_token"] == ""
    assert body["has_value"]["api_token"] is True
    assert "do-not-leak" not in str(body)

    response = client.get("/api/cards/configurable-source/config")
    assert response.status_code == 200
    assert response.get_json()["has_value"]["api_token"] is True
    assert response.get_json()["config"]["api_token"] == ""

    response = client.post(
        "/api/cards/configurable-source/config",
        json={"config": {"api_token": ""}},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert response.get_json()["has_value"]["api_token"] is True

    response = client.post(
        "/api/cards/configurable-source/config",
        json={"config": {"unexpected": "value"}},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 400

    response = client.post(
        "/api/cards/configurable-source/check",
        json={},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert response.get_json()["status"] == "healthy"

    response = client.get("/api/cards/not-loaded/config")
    assert response.status_code == 404



def test_generic_builtin_card_config_rejects_invalid_values_without_writing(tmp_path):
    from moviesync.app import create_app

    app = create_app({"MOVIESYNC_DATA_DIR": str(tmp_path)}, start_scheduler=False)
    services = app.extensions["moviesync"]
    client = app.test_client()
    client.post("/api/setup", json={"username": "admin", "password": "password123"})
    with client.session_transaction() as session:
        csrf = session["csrf_token"]
    headers = {"X-CSRF-Token": csrf}

    config_store = services["config"]
    original_quark = config_store.get_quark_config()
    original_telegram = config_store.get_telegram_config()

    response = client.post(
        "/api/cards/quark/config",
        json={"default_fid": "../invalid"},
        headers=headers,
    )
    assert response.status_code == 400
    assert config_store.get_quark_config() == original_quark

    response = client.post(
        "/api/cards/quark/config",
        json={"category_fids": []},
        headers=headers,
    )
    assert response.status_code == 400
    assert config_store.get_quark_config() == original_quark

    response = client.post(
        "/api/cards/telegram/config",
        json={"channels": [{"id": "bad id"}]},
        headers=headers,
    )
    assert response.status_code == 400
    assert config_store.get_telegram_config() == original_telegram

    response = client.post(
        "/api/cards/telegram/config",
        json={"magic_regex": {"pattern": "(", "replace": "\\1"}},
        headers=headers,
    )
    assert response.status_code == 400
    assert config_store.get_telegram_config() == original_telegram


def test_generic_card_config_runs_card_validator_and_persists_normalized_values(tmp_path):
    from moviesync.app import create_app
    from moviesync.cards import CardManifest, ResourceSourceCard

    app = create_app({"MOVIESYNC_DATA_DIR": str(tmp_path)}, start_scheduler=False)
    services = app.extensions["moviesync"]

    class ValidatingCard(ResourceSourceCard):
        manifest = CardManifest(
            id="validating-source",
            name="Validating Source",
            type="resource_source",
            capabilities=("resource.search", "resource.health_check"),
            config_fields=({"key": "value", "type": "string"},),
        )

        def search(self, movie, config):
            return []

        def check(self, config):
            return {"status": "healthy"}

        def validate_config(self, config):
            normalized = super().validate_config(config)
            normalized["value"] = normalized["value"].strip()
            if not normalized["value"]:
                raise ValueError("value 不能为空")
            return normalized

    services["resource_sources"].register(ValidatingCard())
    client = app.test_client()
    client.post("/api/setup", json={"username": "admin", "password": "password123"})
    with client.session_transaction() as session:
        csrf = session["csrf_token"]
    headers = {"X-CSRF-Token": csrf}

    response = client.post(
        "/api/cards/validating-source/config",
        json={"config": {"value": "  accepted  "}},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.get_json()["config"]["value"] == "accepted"

    response = client.post(
        "/api/cards/validating-source/config",
        json={"config": {"value": "   "}},
        headers=headers,
    )
    assert response.status_code == 400
    assert services["config"].load()["cards"]["validating-source"]["config"]["value"] == "accepted"


def test_disabled_storage_target_returns_clear_error_and_blocks_new_calls(tmp_path):
    from moviesync.app import create_app

    app = create_app({"MOVIESYNC_DATA_DIR": str(tmp_path)}, start_scheduler=False)
    services = app.extensions["moviesync"]
    client = app.test_client()
    client.post("/api/setup", json={"username": "admin", "password": "password123"})
    with client.session_transaction() as session:
        csrf = session["csrf_token"]

    response = client.post(
        "/api/cards/quark/config",
        json={"enabled": False, "config": {}},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200

    resolved = services["storage_targets"].resolve_resource(
        {"pwd_id": "share-1", "storage_target_id": "quark"}
    )
    assert "已停用" in resolved["error"]

    ok, message = services["storage_targets"].transfer(
        {"pwd_id": "share-1"}, [{"fid": "file-1"}], storage_target_id="quark"
    )
    assert ok is False
    assert "已停用" in message

    response = client.post(
        "/api/cards/quark/config",
        json={"enabled": True, "config": {}},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    resolved = services["storage_targets"].resolve_resource(
        {"pwd_id": "share-1", "storage_target_id": "quark"}
    )
    assert "已停用" not in (resolved.get("error") or "")



def test_installed_storage_card_config_and_enable_lifecycle(tmp_path):
    """Installed storage cards use the shared config API and obey enabled state."""
    from moviesync.app import create_app
    from moviesync.cards import CardManifest, StorageTargetCard

    app = create_app({"MOVIESYNC_DATA_DIR": str(tmp_path)}, start_scheduler=False)
    services = app.extensions["moviesync"]

    class PluginStorageCard(StorageTargetCard):
        manifest = CardManifest(
            id="demo-storage-plugin",
            name="Demo Storage Plugin",
            type="storage_target",
            capabilities=("storage.check", "storage.resolve_resource", "storage.list_files",
                          "storage.create_folder", "storage.transfer"),
            config_fields=(
                {"key": "api_token", "label": "API Token", "type": "password",
                 "secret": True, "required": True},
                {"key": "root_id", "label": "Root ID", "type": "string",
                 "default": "root"},
            ),
        )

        def check(self, config):
            return {"status": "healthy" if config.get("api_token") else "unconfigured"}

        def resolve_resource(self, resource):
            return {"files": [], "token": None, "error": None}

        def list_files(self, resource):
            return []

        def create_folder(self, name, parent_id="0"):
            return "folder-id"

        def transfer(self, resource, files, target_id="0"):
            return True, "ok"

    card = PluginStorageCard()
    services["card_registry"].register(card)
    client = app.test_client()
    client.post("/api/setup", json={"username": "admin", "password": "password123"})
    with client.session_transaction() as session:
        csrf = session["csrf_token"]
    headers = {"X-CSRF-Token": csrf}
    endpoint = "/api/cards/demo-storage-plugin/config"

    response = client.post(
        endpoint,
        json={"enabled": True, "config": {"api_token": "secret-token", "root_id": "drive-root"}},
        headers=headers,
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["config"]["api_token"] == ""
    assert body["has_value"]["api_token"] is True
    assert "secret-token" not in response.get_data(as_text=True)
    assert services["config"].load()["cards"]["demo-storage-plugin"]["config"] == {
        "api_token": "secret-token", "root_id": "drive-root"
    }
    assert services["storage_targets"].get("demo-storage-plugin") is card

    response = client.post(
        endpoint,
        json={"enabled": False, "config": {"api_token": "", "root_id": "drive-root"}},
        headers=headers,
    )
    assert response.status_code == 200
    assert services["storage_targets"].get("demo-storage-plugin") is None
    target = next(item for item in services["storage_targets"].list_targets()
                  if item["id"] == "demo-storage-plugin")
    assert target["enabled"] is False
    assert services["config"].load()["cards"]["demo-storage-plugin"]["config"]["api_token"] == "secret-token"

    response = client.post(
        endpoint,
        json={"enabled": True, "config": {"api_token": "", "root_id": "drive-root"}},
        headers=headers,
    )
    assert response.status_code == 200
    assert services["storage_targets"].get("demo-storage-plugin") is card



def test_card_listing_does_not_call_plugin_health_check_and_hides_exception_details(tmp_path):
    from moviesync.app import create_app
    from moviesync.cards import CardManifest, ResourceSourceCard

    app = create_app({"MOVIESYNC_DATA_DIR": str(tmp_path)}, start_scheduler=False)
    services = app.extensions["moviesync"]
    calls = []

    class UnstablePlugin(ResourceSourceCard):
        manifest = CardManifest(
            id="unstable-plugin",
            name="Unstable Plugin",
            type="resource_source",
            capabilities=("resource.search", "resource.health_check"),
            config_fields=({"key": "api_token", "type": "password", "secret": True},),
        )

        def search(self, movie, config):
            return []

        def check(self, config):
            calls.append(config)
            raise RuntimeError("upstream rejected token secret-token-value")

    services["card_registry"].register(UnstablePlugin())
    client = app.test_client()
    client.post("/api/setup", json={"username": "admin", "password": "password123"})
    with client.session_transaction() as session:
        csrf = session["csrf_token"]

    response = client.get("/api/cards")
    assert response.status_code == 200
    item = next(card for card in response.get_json()["cards"] if card["id"] == "unstable-plugin")
    assert item["health"]["status"] == "idle"
    assert item["configured"] is False
    assert calls == []

    response = client.post(
        "/api/cards/unstable-plugin/check",
        json={},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 502
    assert "secret-token-value" not in response.get_data(as_text=True)
    assert "请查看服务日志" in response.get_json()["message"]
    assert len(calls) == 1
