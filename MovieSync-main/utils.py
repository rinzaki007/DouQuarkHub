"""Backward-compatible utility exports."""

from moviesync.clients.douban import DOUBAN_HEADERS
from moviesync.config_store import ConfigStore
from moviesync.settings import PROJECT_ROOT, load_settings


def load_channels():
    settings = load_settings()
    return ConfigStore(settings.config_file, PROJECT_ROOT).get_channels()


def save_channels(channels):
    settings = load_settings()
    ConfigStore(settings.config_file, PROJECT_ROOT).save_channels(channels)


__all__ = ["DOUBAN_HEADERS", "load_channels", "save_channels"]
