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
