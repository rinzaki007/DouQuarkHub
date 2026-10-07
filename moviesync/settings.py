"""MovieSync 运行时设置。

用途：确定数据目录、监听地址、端口、Session Secret、Cookie Secure 和调试模式。
维护说明：Docker 默认使用 /app/data；Secret Key 会自动持久化到 data/.secret_key，避免容器重启导致会话全部失效。
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_CATEGORY_FIDS = {
    "电影": "3ef79d1b370a4b27bd334b7bbba7e6e1",
    "电视剧": "fe24e17d8d254997b21710c73b22b6e7",
    "综艺": "6999ba53a9384525881f785976bd09f1",
    "动漫": "55a44b99fac641679e1ebf55dcb38be9",
}
DEFAULT_OPENLIST_URL = "https://openlist.88888807.xyz:8807/"


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    host: str
    port: int
    secret_key: str
    cookie_secure: bool
    debug: bool

    @property
    def auth_file(self) -> Path:
        return self.data_dir / "auth.json"

    @property
    def config_file(self) -> Path:
        return self.data_dir / "config.json"

    @property
    def subscriptions_file(self) -> Path:
        return self.data_dir / "subscriptions.json"

    @property
    def secret_file(self) -> Path:
        return self.data_dir / ".secret_key"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"


def _load_or_create_secret_key(path: Path) -> str:
    env_value = os.environ.get("SECRET_KEY", "").strip()
    if env_value:
        return env_value

    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value

    value = secrets.token_urlsafe(48)
    path.write_text(value, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return value


def load_settings() -> Settings:
    data_dir = Path(
        os.environ.get(
            "MOVIESYNC_DATA_DIR",
            str(DEFAULT_DATA_DIR),
        )
    ).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    secret_key = _load_or_create_secret_key(
        data_dir / ".secret_key"
    )

    raw_port = os.environ.get(
        "MOVIESYNC_PORT",
        "5000",
    ).strip()

    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ValueError(
            "MOVIESYNC_PORT 必须是 1-65535 的整数"
        ) from exc

    if not 1 <= port <= 65535:
        raise ValueError(
            "MOVIESYNC_PORT 必须是 1-65535 的整数"
        )

    return Settings(
        data_dir=data_dir,
        host=os.environ.get(
            "MOVIESYNC_HOST",
            "0.0.0.0",
        ).strip() or "0.0.0.0",
        port=port,
        secret_key=secret_key,
        cookie_secure=os.environ.get(
            "MOVIESYNC_COOKIE_SECURE",
            "0",
        ).lower() in {"1", "true", "yes"},
        debug=os.environ.get(
            "FLASK_DEBUG",
            "0",
        ).lower() in {"1", "true", "yes"},
    )
