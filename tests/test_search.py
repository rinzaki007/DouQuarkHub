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
