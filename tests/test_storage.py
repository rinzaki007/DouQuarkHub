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



def test_json_store_raises_instead_of_returning_default_on_read_error(tmp_path, monkeypatch):
    import pytest
    from pathlib import Path

    from moviesync.storage import JsonStoreReadError

    path = tmp_path / "protected.json"
    path.write_text('{"keep": true}', encoding="utf-8")
    store = JsonStore(path, lambda: {"fallback": True})
    original_open = Path.open

    def denied_open(self, *args, **kwargs):
        if self == path:
            raise PermissionError("permission denied")
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied_open)

    with pytest.raises(JsonStoreReadError, match="无法读取 JSON 数据文件"):
        store.read()

    assert path.exists()
    with original_open(path, "r", encoding="utf-8") as handle:
        assert handle.read() == '{"keep": true}'



def test_corrupt_json_is_not_replaced_when_quarantine_fails(tmp_path, monkeypatch):
    import pytest

    import moviesync.storage as storage_module
    from moviesync.storage import JsonStoreReadError

    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")
    store = JsonStore(path, lambda: {"fallback": True})

    def denied_replace(*args, **kwargs):
        raise PermissionError("permission denied")

    monkeypatch.setattr(storage_module.os, "replace", denied_replace)

    with pytest.raises(JsonStoreReadError, match="无法隔离损坏的 JSON 数据文件"):
        store.read()

    assert path.exists()
    assert path.read_text(encoding="utf-8") == "{not-json"
