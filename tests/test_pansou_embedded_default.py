


def test_pansou_uses_bundled_service_url_when_card_address_is_empty(monkeypatch):
    monkeypatch.setenv("MOVIESYNC_PANSOU_URL", "http://127.0.0.1:8888")
    http = FakeHttpClient()
    source = PanSouResourceSource(http)

    results = source.search({"title": "测试电影"}, {})

    assert len(results) == 1
    assert http.calls[0][1] == "http://127.0.0.1:8888/api/search"
