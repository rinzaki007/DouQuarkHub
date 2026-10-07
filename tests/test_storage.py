"""JSON 存储层单元测试。

覆盖：原子写入/读取，以及损坏 JSON 回退默认值。
"""
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


def test_corrupt_json_is_quarantined(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")

    assert JsonStore(path, lambda: []).read() == []
    backups = list(tmp_path.glob("broken.json.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{not-json"
