from types import SimpleNamespace

from card_templates.tmdb import TMDBMetadataCard
from moviesync.cards import MetadataProviderCard


class FakeConfigStore:
    def __init__(self, config=None):
        self.config = config or {}

    def get_card_config(self, card_id):
        assert card_id == "tmdb"
        return dict(self.config)


class FakeHttpClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def request_json(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return SimpleNamespace(status_code=200), self.payload


def test_tmdb_card_is_a_standalone_metadata_provider_with_manifest_config():
    card = TMDBMetadataCard(FakeConfigStore())

    assert isinstance(card, MetadataProviderCard)
    assert card.card_id == "tmdb"
    assert card.manifest.type == "metadata_provider"
    assert "metadata.search" in card.capabilities
    assert "metadata.detail" in card.capabilities
    assert card.manifest.image_hosts == ("image.tmdb.org",)
    assert card.manifest.config_fields[0]["key"] == "api_read_access_token"
    assert card.is_configured({"api_read_access_token": "token"}) is True
    assert card.is_configured({}) is False


def test_tmdb_search_uses_bearer_auth_and_normalizes_results():
    payload = {
        "results": [
            {
                "id": 27205,
                "media_type": "movie",
                "title": "盗梦空间",
                "original_title": "Inception",
                "poster_path": "/poster.jpg",
                "backdrop_path": "/backdrop.jpg",
                "release_date": "2010-07-15",
                "vote_average": 8.4,
                "vote_count": 30000,
                "overview": "梦境中的任务",
                "genre_ids": [878, 53],
            },
            {"id": 999, "media_type": "person", "name": "Ignored"},
        ]
    }
    http = FakeHttpClient(payload)
    card = TMDBMetadataCard(
        FakeConfigStore({"api_read_access_token": "private-token", "language": "zh-CN"}),
        http,
    )

    result = card.search("盗梦空间")

    assert len(result) == 1
    assert result[0]["id"] == "movie:27205"
    assert result[0]["tmdb_id"] == "27205"
    assert result[0]["media_type"] == "movie"
    assert result[0]["title"] == "盗梦空间"
    assert result[0]["original_title"] == "Inception"
    assert result[0]["cover"] == "https://image.tmdb.org/t/p/w500/poster.jpg"
    assert result[0]["backdrop"] == "https://image.tmdb.org/t/p/w1280/backdrop.jpg"
    assert result[0]["year"] == "2010"
    assert result[0]["rate"] == "8.4"
    assert result[0]["provider_id"] == "tmdb"
    assert result[0]["provider_name"] == "TMDB"
    assert http.calls[0][1] == "https://api.themoviedb.org/3/search/multi"
    assert http.calls[0][2]["headers"]["Authorization"] == "Bearer private-token"
    assert http.calls[0][2]["params"]["language"] == "zh-CN"
    assert "private-token" not in http.calls[0][1]


def test_tmdb_search_caches_results_and_does_not_request_without_token():
    empty_http = FakeHttpClient({"results": []})
    empty_card = TMDBMetadataCard(FakeConfigStore(), empty_http)
    assert empty_card.search("test") == []
    assert empty_http.calls == []

    http = FakeHttpClient({"results": [{"id": 1, "media_type": "tv", "name": "测试剧"}]})
    card = TMDBMetadataCard(
        FakeConfigStore({"api_read_access_token": "private-token"}),
        http,
    )

    assert card.search("测试剧")[0]["media_type"] == "tv"
    assert card.search("测试剧")[0]["title"] == "测试剧"
    assert len(http.calls) == 1


def test_tmdb_list_maps_categories_and_rating_sort():
    http = FakeHttpClient({"results": [{"id": 2, "title": "测试电影", "release_date": "2024-01-01"}]})
    card = TMDBMetadataCard(
        FakeConfigStore({"api_read_access_token": "token"}),
        http,
    )

    result = card.list_movies("电影", "R")

    assert result[0]["title"] == "测试电影"
    assert http.calls[0][1] == "https://api.themoviedb.org/3/discover/movie"
    assert http.calls[0][2]["params"]["sort_by"] == "vote_average.desc"
    assert http.calls[0][2]["params"]["vote_count.gte"] == 100


def test_tmdb_details_return_external_ids_and_health_check_never_exposes_token():
    http = FakeHttpClient({
        "id": 123,
        "name": "测试剧",
        "first_air_date": "2022-05-01",
        "external_ids": {"imdb_id": "tt123"},
    })
    card = TMDBMetadataCard(
        FakeConfigStore({"api_read_access_token": "secret-token"}),
        http,
    )

    detail = card.get_detail("tv:123")

    assert detail["id"] == "tv:123"
    assert detail["external_ids"] == {"imdb_id": "tt123"}
    assert card.check({}) == {
        "status": "unconfigured",
        "message": "请先填写 TMDB API Read Access Token",
    }
    assert "secret-token" not in str(card.check({"api_read_access_token": "secret-token"}))
