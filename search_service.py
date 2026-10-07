"""Backward-compatible adapter for the pre-refactor SearchService constructor."""

import logging

from moviesync.clients.quark import QuarkClient
from moviesync.clients.telegram import TelegramClient
from moviesync.services.search import SearchService as _SearchService


class SearchService(_SearchService):
    def __init__(self, cookie):
        super().__init__(QuarkClient(cookie), TelegramClient(), logging.getLogger("moviesync"))


__all__ = ["SearchService"]
