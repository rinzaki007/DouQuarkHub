"""Tests for global filename recognition shared across resource sources."""
from moviesync.cards import CardManifest, CardRegistry, FilenameProcessorCard
from card_templates.filename_recognition import FilenameRecognitionCard
from moviesync.services.filename_rules import parse_tv_episode
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
    registry = CardRegistry()
    registry.register(FilenameRecognitionCard())
    manager = ResourceSourceManager(
        FakeConfigStore(), FakeLogger(), registry=registry
    )

    assert manager.parse_tv_episode("pansou", "Show-Episode-12.mkv") == (1, 12)


def test_filename_processor_is_discovered_by_type_not_fixed_card_id():
    class CustomFilenameProcessor(FilenameProcessorCard):
        manifest = CardManifest(
            id="custom_episode_rules",
            name="Custom episode rules",
            type="filename_processor",
            capabilities=("filename.parse",),
        )

        def parse_episode(self, file_name, config):
            magic = config.get("magic_regex", {})
            return parse_tv_episode(file_name, magic)

    class ConfigStore:
        def load(self):
            return {
                "cards": {
                    "custom_episode_rules": {
                        "enabled": True,
                        "config": {
                            "magic_regex": {
                                "pattern": "^Custom-Episode-([0-9]+)[.]mkv$",
                                "replace": r"Show.S01E\\1.mkv",
                            }
                        },
                    }
                }
            }

    registry = CardRegistry()
    registry.register(CustomFilenameProcessor())
    manager = ResourceSourceManager(ConfigStore(), FakeLogger(), registry=registry)

    assert manager.parse_tv_episode(
        "some-resource-source", "Custom-Episode-12.mkv"
    ) == (1, 12)

def test_global_filename_card_rejects_invalid_regex():
    import pytest

    from card_templates.filename_recognition import FilenameRecognitionCard
    from moviesync.errors import ConfigValidationError

    card = FilenameRecognitionCard()
    with pytest.raises(ConfigValidationError, match="规则无效"):
        card.validate_config({
            "magic_regex": {"pattern": "(", "replace": ""}
        })
