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
    assert body["config"]["has_api_token"] is True
    assert "api_token" not in body["config"]

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
