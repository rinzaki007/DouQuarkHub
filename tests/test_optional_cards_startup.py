"""Regression coverage for optional-card startup and homepage navigation."""

from moviesync import app as app_module


def _create_test_app(tmp_path, monkeypatch):
    # Production defaults to an empty card directory; existing tests that need
    # bundled cards opt in through tests/conftest.py.
    monkeypatch.setenv("MOVIESYNC_AUTO_INSTALL_BUNDLED_CARDS", "0")
    return app_module.create_app(
        {"MOVIESYNC_DATA_DIR": str(tmp_path)},
        start_scheduler=False,
    )


def test_app_starts_and_core_pages_render_without_any_cards(tmp_path, monkeypatch):
    app = _create_test_app(tmp_path, monkeypatch)
    app.testing = True
    client = app.test_client()

    try:
        assert client.get("/").status_code == 200
        assert client.get("/tasks").status_code == 200
        assert client.get("/admin").status_code == 200
        assert client.get("/healthz").status_code == 200
        assert app.extensions["moviesync"]["card_registry"].list() == []
        assert list((tmp_path / "cards").glob("*.py")) == []
    finally:
        app.extensions["moviesync"]["shutdown"]()


def test_broken_card_does_not_prevent_a_valid_card_from_loading(tmp_path, monkeypatch):
    card_dir = tmp_path / "cards"
    card_dir.mkdir(parents=True)
    (card_dir / "broken.py").write_text("this is not valid python !!!", encoding="utf-8")
    (card_dir / "healthy.py").write_text(
        "from moviesync.cards import Card, CardManifest\n"
        "class HealthyCard(Card):\n"
        "    manifest = CardManifest(id='healthy', name='Healthy card', type='custom')\n"
        "def create_card(context):\n"
        "    return HealthyCard()\n",
        encoding="utf-8",
    )

    app = _create_test_app(tmp_path, monkeypatch)
    app.testing = True
    services = app.extensions["moviesync"]

    try:
        registry = services["card_registry"]
        assert registry.get("healthy") is not None
        plugins = {item["filename"]: item for item in services["file_card_plugins"].list_plugins()}
        assert plugins["healthy.py"]["loaded"] is True
        assert plugins["broken.py"]["loaded"] is False
        assert plugins["broken.py"]["error"]
        assert app.test_client().get("/").status_code == 200
    finally:
        services["shutdown"]()


def test_about_link_is_only_in_the_homepage_footer(tmp_path, monkeypatch):
    app = _create_test_app(tmp_path, monkeypatch)
    app.testing = True
    try:
        html = app.test_client().get("/").get_data(as_text=True)
        assert 'href="/about"' in html
        assert html.index("</main>") < html.index('href="/about"')
        assert 'href="/admin"' in html
    finally:
        app.extensions["moviesync"]["shutdown"]()


def test_bundled_cards_can_be_installed_explicitly(tmp_path, monkeypatch):
    monkeypatch.setenv("MOVIESYNC_AUTO_INSTALL_BUNDLED_CARDS", "1")
    app = app_module.create_app(
        {"MOVIESYNC_DATA_DIR": str(tmp_path)},
        start_scheduler=False,
    )
    services = app.extensions["moviesync"]
    try:
        assert services["card_registry"].get("pansou") is not None
        assert (tmp_path / "cards" / "pansou.py").is_file()
    finally:
        services["shutdown"]()
