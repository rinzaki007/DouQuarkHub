from moviesync.services.search import SearchService


class FakeTelegram:
    def search_channel(self, channel, title):
        return [
            {"channel": channel["name"], "pwd_id": "same123"},
            {"channel": channel["name"], "pwd_id": "same123"},
        ]


class FakeQuark:
    def get_share_files(self, pwd_id):
        return ([{"fid": "f1", "file_name": "Show.S01E01.1080p.mkv", "size": 1}], "token", None)


def test_search_deduplicates_share_ids_and_is_stable():
    import logging

    service = SearchService(FakeQuark(), FakeTelegram(), logging.getLogger("test"))
    candidates = service.search_movie_candidates({"title": "Show"}, [
        {"name": "first", "id": "first_channel"},
        {"name": "second", "id": "second_channel"},
    ])
    assert len(candidates) == 1
    assert candidates[0]["channel"] == "first"
    assert "stoken" not in candidates[0]
