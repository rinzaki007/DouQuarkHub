import json

from moviesync.storage import JsonStore


def test_json_store_writes_atomically(tmp_path):
    path = tmp_path / "config.json"
    store = JsonStore(path, lambda: {})
    store.write({"hello": "世界"})
    assert json.loads(path.read_text(encoding="utf-8")) == {"hello": "世界"}
    assert store.read() == {"hello": "世界"}


def test_json_store_returns_default_for_corrupt_json(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")
    assert JsonStore(path, lambda: []).read() == []
