"""Backward-compatible adapter for the pre-refactor SubscriptionManager constructor."""

from moviesync.clients.quark import clean_tv_filename
from moviesync.logging_setup import configure_logging
from moviesync.services.subscriptions import SubscriptionManager as _SubscriptionManager
from moviesync.settings import load_settings


class SubscriptionManager(_SubscriptionManager):
    def __init__(self, get_cookie_func):
        settings = load_settings()
        logger = configure_logging(settings.log_dir)
        super().__init__(settings.subscriptions_file, get_cookie_func, logger)


__all__ = ["SubscriptionManager", "clean_tv_filename"]
