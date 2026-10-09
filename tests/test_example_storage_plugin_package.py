import importlib.metadata
import subprocess
import sys
from pathlib import Path

from moviesync.cards import CardRegistry
from moviesync.services.storage_targets import StorageTargetManager


class PluginConfig:
    def load(self):
        return {"cards": {"example-storage": {"enabled": True, "config": {"display_name": "CI Demo"}}}}

    def get_default_storage_target_id(self):
        return "example-storage"


class PluginLogger:
    def exception(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass


def test_example_storage_package_installs_and_loads_through_entry_point(tmp_path, monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    package_dir = repo_root / "examples" / "storage-card-plugin"
    install_dir = tmp_path / "installed-plugin"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-deps",
            "--no-build-isolation",
            "--target",
            str(install_dir),
            str(package_dir),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    monkeypatch.syspath_prepend(str(install_dir))

    entry_points = importlib.metadata.entry_points(group="moviesync.storage_targets")
    assert any(
        entry_point.name == "example-storage"
        and entry_point.value == "moviesync_example_storage:create_card"
        for entry_point in entry_points
    )

    registry = CardRegistry()
    config = PluginConfig()
    logger = PluginLogger()
    manager = StorageTargetManager(registry, config, logger)

    loaded = manager.load_plugins({"config_store": config, "logger": logger})

    assert "example-storage" in loaded
    card = registry.get("example-storage")
    assert card is not None
    assert card.manifest.name == "示例存储（仅演示）"
    assert card.check({"display_name": "CI Demo"})["status"] == "healthy"
    assert card.destination_options()[0]["id"] == "demo-root"
    assert card.transfer({}, [], "demo-root") == (
        False,
        "这是示例插件，不会执行真实转存",
    )
