"""资源搜索服务单元测试。

使用 Fake Telegram/Quark，验证多频道搜索结果按分享 ID 去重且顺序稳定，并确保 stoken 不泄露到候选结果。
"""
from moviesync.services.search import SearchService


class FakeResourceSources:
    def search(self, movie, config):
        return [
            {"source_id": "telegram", "source_name": "Telegram", "channel": "first", "pwd_id": "same123"},
            {"source_id": "telegram", "source_name": "Telegram", "channel": "first", "pwd_id": "same123"},
        ]


class FakeStorageTargets:
    def resolve_resource(self, resource, target_id=None):
        return {
            "target_id": target_id or "quark",
            "files": [{"fid": "f1", "file_name": "Show.S01E01.1080p.mkv", "size": 1}],
            "token": "token",
            "error": None,
        }


def test_search_deduplicates_share_ids_and_is_stable():
    import logging

    service = SearchService(FakeResourceSources(), FakeStorageTargets(), logging.getLogger("test"))
    candidates = service.search_movie_candidates({"title": "Show"}, {"channels": []})
    assert len(candidates) == 1
    assert candidates[0]["channel"] == "first"
    assert "stoken" not in candidates[0]


class FakeDoubanResponse:
    status_code = 200


class FakeDoubanHttp:
    def request_json(self, *args, **kwargs):
        return FakeDoubanResponse(), [
            {
                "title": "测试电影",
                "img": "https://example.com/poster.jpg",
                "year": "2025",
                "id": "1234567",
            }
        ]


def test_douban_search_does_not_use_year_as_rating(monkeypatch):
    from moviesync.clients.douban import DoubanClient

    client = DoubanClient()
    monkeypatch.setattr(client, "http", FakeDoubanHttp())

    results = client.search("测试电影")

    assert len(results) == 1
    assert results[0]["title"] == "测试电影"
    assert results[0]["year"] == "2025"
    assert results[0]["rate"] == "暂无"


def test_folder_creation_exception_is_not_returned_to_user():
    import logging

    class ExplodingStorageTargets(FakeStorageTargets):
        def create_folder(self, *_args, **_kwargs):
            raise RuntimeError("upstream cookie=SECRET_COOKIE_VALUE")

    service = SearchService(
        FakeResourceSources(),
        ExplodingStorageTargets(),
        logging.getLogger("test"),
    )

    ok, message, _counts = service.transfer_selected_resource_with_progress(
        {"title": "Show"},
        {"pwd_id": "same123", "files": [{"fid": "f1"}]},
        "0",
    )

    assert ok is False
    assert message == "创建专属文件夹失败: 请检查存储目标配置或查看服务日志"
    assert "SECRET_COOKIE_VALUE" not in message


def test_resource_resolution_error_is_not_returned_to_transfer_task():
    import logging

    class ExplodingResolveTargets(FakeStorageTargets):
        def resolve_resource(self, resource, target_id=None):
            return {
                "target_id": "quark",
                "files": [],
                "token": None,
                "error": "upstream cookie=SECRET_COOKIE_VALUE",
            }

    service = SearchService(
        FakeResourceSources(),
        ExplodingResolveTargets(),
        logging.getLogger("test"),
    )

    ok, message, _counts = service.transfer_selected_resource_with_progress(
        {"title": "Show"},
        {"pwd_id": "same123", "files": [{"fid": "f1"}]},
        "0",
    )

    assert ok is False
    assert message == "分享资源解析失败，请检查分享链接或查看服务日志"
    assert "SECRET_COOKIE_VALUE" not in message


def test_transfer_plugin_failure_message_is_sanitized():
    import logging

    class ExplodingTransferTargets(FakeStorageTargets):
        def create_folder(self, *_args, **_kwargs):
            return "folder-1"

        def transfer(self, *_args, **_kwargs):
            return False, "upstream cookie=SECRET_COOKIE_VALUE"

    service = SearchService(
        FakeResourceSources(),
        ExplodingTransferTargets(),
        logging.getLogger("test"),
    )

    ok, message, counts = service.transfer_selected_resource_with_progress(
        {"title": "Show"},
        {"pwd_id": "same123", "files": [{"fid": "f1"}]},
        "0",
    )

    assert ok is False
    assert message == "转存失败，请检查存储目标配置或查看服务日志"
    assert counts["uncertain"] is False
    assert "SECRET_COOKIE_VALUE" not in message



def test_transfer_refreshes_share_state_and_temporary_token():
    import logging

    class RotatingTokenStorage(FakeStorageTargets):
        def __init__(self):
            self.resolve_count = 0
            self.transfer_token = None

        def resolve_resource(self, resource, target_id=None):
            self.resolve_count += 1
            return {
                "target_id": target_id or "quark",
                "files": [
                    {"fid": "f1", "file_name": "Show.S01E01.1080p.mkv", "size": 1}
                ],
                "token": f"token-{self.resolve_count}",
                "error": None,
            }

        def create_folder(self, *_args, **_kwargs):
            return "folder-1"

        def transfer(self, resource, files, target_id="0", storage_target_id=None, token=None):
            self.transfer_token = token
            return True, "ok"

    storage = RotatingTokenStorage()
    service = SearchService(FakeResourceSources(), storage, logging.getLogger("test"))
    resource = {"pwd_id": "same123", "storage_target_id": "quark"}

    # Search can populate the short-lived cache, but its token must not be reused for transfer.
    _files, search_token, _error, _target_id = service._get_resource_files(resource)
    assert search_token == "token-1"

    ok, _message, _counts = service.transfer_selected_resource_with_progress(
        {"title": "Show"},
        {"pwd_id": "same123", "storage_target_id": "quark", "files": [{"fid": "f1"}]},
        "0",
    )

    assert ok is True
    assert storage.resolve_count == 2
    assert storage.transfer_token == "token-2"
