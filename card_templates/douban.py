"""Standalone Douban metadata-provider card shipped as one Python file."""
from __future__ import annotations

from typing import Any

from moviesync.cards import CardManifest, MetadataProviderCard
from moviesync.clients.douban import DoubanClient


class DoubanMetadataCard(MetadataProviderCard):
    manifest = CardManifest(
        id="douban",
        name="Douban",
        version="1.0.0",
        type="metadata_provider",
        description="豆瓣影视元数据与搜索",
        capabilities=("metadata.list", "metadata.search"),
    )

    def __init__(self, client: DoubanClient):
        self.client = client

    def list_movies(self, tag: str, sort_type: str) -> list[dict[str, Any]]:
        return self.client.get_movies(tag, sort_type)

    def search(self, query: str) -> list[dict[str, Any]]:
        return self.client.search(query)

    def get_detail(self, item_id: str) -> dict[str, Any] | None:
        return None


def create_card(context):
    """Create the metadata card using the shared Douban client."""
    return DoubanMetadataCard(context["douban"])
