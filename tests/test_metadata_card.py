from moviesync.cards import MetadataProviderCard
from moviesync.cards_metadata import DoubanMetadataCard


class FakeDouban:
    def get_movies(self, tag, sort_type):
        return [{"title": tag, "sort": sort_type}]

    def search(self, query):
        return [{"title": query}]


def test_douban_metadata_card_uses_standard_interface():
    card = DoubanMetadataCard(FakeDouban())

    assert isinstance(card, MetadataProviderCard)
    assert card.card_id == "douban"
    assert "metadata.list" in card.capabilities
    assert card.list_movies("电影", "U") == [{"title": "电影", "sort": "U"}]
    assert card.search("测试") == [{"title": "测试"}]
    assert card.get_detail("123") is None
