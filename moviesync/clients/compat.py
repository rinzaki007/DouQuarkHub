"""Backward-compatible lazy adapter for legacy cards expecting a shared Telegram client.

New cards should construct and own their platform clients. This adapter exists only
for older extensions that still receive context["telegram"] or the legacy
app.extensions["moviesync"]["telegram"] service.
"""
from __future__ import annotations

from threading import RLock
from typing import Any


class LazyTelegramClient:
    """Proxy TelegramClient without importing or constructing it until first use."""

    def __init__(self) -> None:
        self._client: Any = None
        self._lock = RLock()

    def _get_client(self):
        if self._client is None:
            with self._lock:
                if self._client is None:
                    from .telegram import TelegramClient

                    self._client = TelegramClient()
        return self._client

    def __getattr__(self, name: str):
        return getattr(self._get_client(), name)

    def close(self) -> None:
        """Release the lazy client HTTP session if it was ever created."""
        client = self._client
        if client is None:
            return
        http = getattr(client, "http", None)
        session = getattr(http, "session", None)
        close = getattr(session, "close", None)
        if callable(close):
            close()
