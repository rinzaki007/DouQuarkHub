from __future__ import annotations

from types import SimpleNamespace

from card_templates.aliyun import AliyunDriveStorageCard, _share_id


class FakeStore:
    def __init__(self, config=None):
        self.config = dict(config or {})

    def get_card_config(self, card_id):
        assert card_id == "aliyun"
        return dict(self.config)

    def save_card_config(self, card_id, config):
        self.config.update(config)


class FakeHTTP:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request_json(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        status, data = self.responses.pop(0)
        return SimpleNamespace(status_code=status), data


def test_aliyun_card_manifest_declares_only_aliyun_share_compatibility():
    card = AliyunDriveStorageCard(FakeStore())
    assert card.card_id == "aliyun"
    assert "storage.accepts.aliyun_share" in card.manifest.capabilities
    assert "storage.accepts.quark_share" not in card.manifest.capabilities


def test_aliyun_share_id_accepts_share_urls_and_rejects_other_hosts():
    assert _share_id({"url": "https://www.alipan.com/s/AbC123"}) == "AbC123"
    assert _share_id({"url": "https://www.aliyundrive.com/s/AbC123/folder/123"}) == "AbC123"
    assert _share_id({"url": "https://pan.quark.cn/s/AbC123"}) == ""
    assert _share_id({"resource_id": "AbC123"}) == "AbC123"
    assert _share_id({"resource_id": "../etc/passwd"}) == ""


def test_aliyun_card_requires_own_open_platform_credentials():
    card = AliyunDriveStorageCard(FakeStore())
    assert card.is_configured({}) is False
    assert card.is_configured({"refresh_token": "token"}) is False
    assert card.is_configured({"client_id": "app-id", "refresh_token": "token"}) is False
    assert card.is_configured({
        "client_id": "app-id",
        "client_secret": "app-secret",
        "refresh_token": "token",
    }) is True
    assert card.check({})["status"] == "unconfigured"


def test_aliyun_login_fails_fast_without_app_credentials():
    http = FakeHTTP([])
    card = AliyunDriveStorageCard(FakeStore({"refresh_token": "openlist-token"}), http)
    try:
        card._ensure_login()
    except RuntimeError as exc:
        assert "App ID" in str(exc)
    else:
        raise AssertionError("missing app credentials should be rejected")
    assert http.calls == []


def test_aliyun_login_refreshes_with_own_app_credentials_and_persists_rotated_token():
    store = FakeStore({
        "client_id": "my-app-id",
        "client_secret": "my-app-secret",
        "refresh_token": "old-refresh",
    })
    http = FakeHTTP([
        (200, {
            "access_token": "access",
            "refresh_token": "rotated-refresh",
            "expires_in": 3600,
            "default_drive_id": "drive-123",
        }),
    ])
    card = AliyunDriveStorageCard(store, http)
    card._request = lambda method, url, **kwargs: http.request_json(method, url, **kwargs)[1]
    access_token, drive_id = card._ensure_login()
    assert access_token == "access"
    assert drive_id == "drive-123"
    request = http.calls[0]
    assert request[1].endswith("/oauth/access_token")
    assert request[2]["json"] == {
        "grant_type": "refresh_token",
        "refresh_token": "old-refresh",
        "client_id": "my-app-id",
        "client_secret": "my-app-secret",
    }
    assert store.config["refresh_token"] == "rotated-refresh"
    assert store.config["client_id"] == "my-app-id"
    assert store.config["client_secret"] == "my-app-secret"


def test_aliyun_login_uses_open_api_to_discover_default_drive_id():
    store = FakeStore({
        "client_id": "my-app-id",
        "client_secret": "my-app-secret",
        "refresh_token": "refresh",
    })
    http = FakeHTTP([
        (200, {"access_token": "access", "expires_in": 3600}),
        (200, {"default_drive_id": "drive-from-open-api"}),
    ])
    card = AliyunDriveStorageCard(store, http)
    card._request = lambda method, url, **kwargs: http.request_json(method, url, **kwargs)[1]
    access_token, drive_id = card._ensure_login()
    assert access_token == "access"
    assert drive_id == "drive-from-open-api"
    assert http.calls[0][1] == "https://openapi.aliyundrive.com/oauth/access_token"
    assert http.calls[1][1] == "https://openapi.aliyundrive.com/adrive/v1.0/user/getDriveInfo"


def test_aliyun_resolve_share_normalizes_files_and_recurses():
    store = FakeStore({"refresh_token": "refresh"})
    http = FakeHTTP([
        (200, {"share_token": "share-token"}),
        (200, {"items": [
            {"file_id": "folder-1", "name": "Season 1", "type": "folder"},
            {"file_id": "video-1", "name": "S01E01.mkv", "type": "file", "size": 123},
        ], "next_marker": ""}),
        (200, {"items": [
            {"file_id": "video-2", "name": "S01E02.mkv", "type": "file", "size": 456},
        ], "next_marker": ""}),
    ])
    card = AliyunDriveStorageCard(store, http)
    card._request = lambda method, url, **kwargs: http.request_json(method, url, **kwargs)[1]
    result = card.resolve_resource({
        "resource_id": "Share123",
        "resource_type": "aliyun_share",
        "password": "1234",
    })
    assert result["error"] is None
    assert result["token"] == "share-token"
    assert [item["fid"] for item in result["files"]] == ["video-2", "video-1"]
    assert result["files"][0]["file_name"] == "S01E02.mkv"


def test_aliyun_card_reports_missing_share_id_without_network_calls():
    http = FakeHTTP([])
    card = AliyunDriveStorageCard(FakeStore({"refresh_token": "refresh"}), http)
    result = card.resolve_resource({"resource_type": "aliyun_share"})
    assert result["files"] == []
    assert "无效" in result["error"]
    assert http.calls == []
