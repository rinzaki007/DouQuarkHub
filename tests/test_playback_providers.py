from __future__ import annotations

from types import SimpleNamespace

import pytest

from moviesync.app import create_app
from moviesync.card_plugins import CardFilePluginManager
from moviesync.cards import CardManifest, CardRegistry, PlaybackProviderCard
from moviesync.clients.quark import QuarkClient
from moviesync.services.playback_providers import PlaybackProviderManager


class FakePlaybackCard(PlaybackProviderCard):
    manifest = CardManifest(
        id="fake-playback",
        name="Fake Playback",
        type="playback_provider",
        capabilities=("playback.list_files", "playback.resolve"),
    )

    def is_configured(self, config):
        return True

    def list_files(self, parent_fid="0"):
        return [{"fid": "video-1", "file_name": "sample.mp4", "is_dir": False, "is_video": True}]

    def resolve_playback(self, fid):
        return {
            "fid": fid,
            "file_name": "sample.mp4",
            "url": "https://media.example/video.mp4",
            "mime_type": "video/mp4",
        }


class FakeStore:
    def load(self):
        return {"cards": {}}


class FakeLogger:
    def exception(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass


def test_playback_provider_manager_dispatches_by_card_contract_and_honors_disabled_state():
    registry = CardRegistry()
    registry.register(FakePlaybackCard())
    store = FakeStore()
    manager = PlaybackProviderManager(registry, store, FakeLogger())

    assert manager.list_providers() == [{
        "id": "fake-playback",
        "name": "Fake Playback",
        "description": "",
        "configured": True,
    }]
    assert manager.list_files("fake-playback", "0")[0]["fid"] == "video-1"
    assert manager.resolve_playback("fake-playback", "video-1")["url"].startswith("https://")

    store.load = lambda: {"cards": {"fake-playback": {"enabled": False, "config": {}}}}
    assert manager.list_providers() == []
    with pytest.raises(LookupError, match="已停用"):
        manager.list_files("fake-playback", "0")


def test_quark_client_persists_refreshed_session_cookies_for_followup_requests(monkeypatch):
    client = QuarkClient("foo=old; __pus=old-pus")
    response = SimpleNamespace(
        status_code=200,
        cookies=SimpleNamespace(get_dict=lambda: {"__pus": "new-pus", "__puus": "new-puus"}),
    )
    monkeypatch.setattr(client.http, "request_json", lambda *args, **kwargs: (response, {"code": 0}))

    client._request_json("GET", "https://drive.quark.cn/example", timeout=2)

    assert "foo=old" in client.get_cookie()
    assert "__pus=new-pus" in client.get_cookie()
    assert "__puus=new-puus" in client.get_cookie()
    assert client.http.headers["Cookie"] == client.get_cookie()
