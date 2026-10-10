"""Tests for global filename recognition shared across resource sources."""
from moviesync.cards import CardRegistry
from moviesync.services.resource_sources import ResourceSourceManager


class FakeConfigStore:
    def load(self):
        return {
            "cards": {
                "filename_recognition": {
                    "enabled": True,
                    "config": {
                        "magic_regex": {
                            "pattern": "^Show-Episode-([0-9]+)[.]mkv$",
                            "replace": r"Show.S01E\1.mkv",
                        }
                    },
                }
            }
        }


class FakeLogger:
    def exception(self, *args, **kwargs):
        pass


def test_global_filename_rules_apply_without_a_telegram_source():
    manager = ResourceSourceManager(
        FakeConfigStore(), FakeLogger(), registry=CardRegistry()
    )

    assert manager.parse_tv_episode("pansou", "Show-Episode-12.mkv") == (1, 12)
