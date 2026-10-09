from moviesync.app import create_app
from moviesync.cards import CardManifest, ResourceSourceCard


def test_card_manifest_text_constraints_reject_invalid_config_without_writing(tmp_path):
    app = create_app({"MOVIESYNC_DATA_DIR": str(tmp_path)}, start_scheduler=False)
    services = app.extensions["moviesync"]

    class ConstrainedCard(ResourceSourceCard):
        manifest = CardManifest(
            id="constrained-source",
            name="Constrained Source",
            type="resource_source",
            capabilities=("resource.search", "resource.health_check"),
            config_fields=(
                {
                    "key": "endpoint",
                    "label": "Endpoint",
                    "type": "string",
                    "required": True,
                    "format": "url",
                    "max_length": 24,
                },
                {
                    "key": "slug",
                    "label": "Slug",
                    "type": "string",
                    "required": True,
                    "min_length": 3,
                    "max_length": 12,
                    "pattern": "^[a-z0-9-]+$",
                },
            ),
        )

        def search(self, movie, config):
            return []

        def check(self, config):
            return {"status": "healthy"}

    services["resource_sources"].register(ConstrainedCard())
    client = app.test_client()
    client.post("/api/setup", json={"username": "admin", "password": "password123"})
    with client.session_transaction() as session:
        csrf = session["csrf_token"]
    headers = {"X-CSRF-Token": csrf}
    endpoint = "/api/cards/constrained-source/config"

    valid = {"endpoint": "https://example.com", "slug": "movie-source"}
    response = client.post(endpoint, json={"config": valid}, headers=headers)
    assert response.status_code == 200
    assert services["config"].load()["cards"]["constrained-source"]["config"] == valid

    invalid_values = [
        ({"endpoint": "ftp://example.com", "slug": "movie-source"}, "HTTP 或 HTTPS"),
        ({"endpoint": "https://example.com/a-very-long-path", "slug": "movie-source"}, "不能超过 24"),
        ({"endpoint": "https://example.com", "slug": "Movie_Source"}, "格式不正确"),
        ({"endpoint": "https://example.com", "slug": "ab"}, "不能少于 3"),
    ]
    for invalid_config, expected_message in invalid_values:
        response = client.post(endpoint, json={"config": invalid_config}, headers=headers)
        assert response.status_code == 400
        assert expected_message in response.get_json()["message"]
        assert services["config"].load()["cards"]["constrained-source"]["config"] == valid
