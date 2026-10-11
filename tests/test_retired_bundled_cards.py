from __future__ import annotations

from moviesync import card_plugins


class FakeLogger:
    def info(self, *args, **kwargs):
        pass

    def exception(self, *args, **kwargs):
        pass


def test_removed_bundled_card_is_cleaned_up_only_when_unmodified(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled"
    plugin_dir = tmp_path / "data" / "cards"
    marker_dir = plugin_dir / ".seeded"
    bundled.mkdir()
    marker_dir.mkdir(parents=True)

    filename = "aliyun.py"
    old_content = b'"""old bundled card"""\n'
    blob = card_plugins._git_blob_sha(old_content)
    monkeypatch.setattr(card_plugins, "_RETIRED_BUNDLED_CARD_BLOBS", {filename: {blob}})

    # A known old bundled copy with a legacy empty marker can be safely removed.
    (plugin_dir / filename).write_bytes(old_content)
    (marker_dir / f"{filename}.seeded").write_text("", encoding="ascii")

    manager = card_plugins.CardFilePluginManager(
        plugin_dir,
        card_plugins.CardRegistry(),
        FakeLogger(),
        bundled,
        seed_missing=False,
    )

    assert not (plugin_dir / filename).exists()
    assert not (marker_dir / f"{filename}.seeded").exists()
    assert manager.list_plugins() == []


def test_removed_bundled_card_preserves_customized_files(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled"
    plugin_dir = tmp_path / "data" / "cards"
    marker_dir = plugin_dir / ".seeded"
    bundled.mkdir()
    marker_dir.mkdir(parents=True)

    filename = "aliyun.py"
    customized = b'"""administrator-edited card"""\n'
    blob = card_plugins._git_blob_sha(customized)
    monkeypatch.setattr(card_plugins, "_RETIRED_BUNDLED_CARD_BLOBS", {filename: {"different-known-blob"}})

    (plugin_dir / filename).write_bytes(customized)
    (marker_dir / f"{filename}.seeded").write_text(f"customized:{blob}", encoding="ascii")

    card_plugins.CardFilePluginManager(
        plugin_dir,
        card_plugins.CardRegistry(),
        FakeLogger(),
        bundled,
        seed_missing=False,
    )

    assert (plugin_dir / filename).read_bytes() == customized
    assert (marker_dir / f"{filename}.seeded").read_text(encoding="ascii") == f"customized:{blob}"



def test_exact_retired_card_upload_without_marker_is_removed(tmp_path, monkeypatch):
    bundled = tmp_path / "bundled"
    plugin_dir = tmp_path / "data" / "cards"
    bundled.mkdir()
    plugin_dir.mkdir(parents=True)

    filename = "aliyun.py"
    old_content = b'"""exact retired card uploaded by the user"""\n'
    blob = card_plugins._git_blob_sha(old_content)
    monkeypatch.setattr(card_plugins, "_RETIRED_BUNDLED_CARD_BLOBS", {filename: {blob}})
    (plugin_dir / filename).write_bytes(old_content)

    card_plugins.CardFilePluginManager(
        plugin_dir,
        card_plugins.CardRegistry(),
        FakeLogger(),
        bundled,
        seed_missing=False,
    )

    assert not (plugin_dir / filename).exists()
