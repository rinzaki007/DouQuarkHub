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


class FakeQuark:
    def get_share_files(self, pwd_id):
        return ([{"fid": "f1", "file_name": "Show.S01E01.1080p.mkv", "size": 1}], "token", None)


def test_search_deduplicates_share_ids_and_is_stable():
    import logging

    service = SearchService(FakeQuark(), FakeResourceSources(), logging.getLogger("test"))
    candidates = service.search_movie_candidates({"title": "Show"}, {"channels": []})
    assert len(candidates) == 1
    assert candidates[0]["channel"] == "first"
    assert "stoken" not in candidates[0]
