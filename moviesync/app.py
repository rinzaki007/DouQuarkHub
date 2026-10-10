"""MovieSync 应用组装层。

用途：加载设置、初始化认证/配置/豆瓣/Telegram/夸克/订阅等组件，组装 Flask 应用并注册 Web 路由。
维护说明：这里主要负责依赖注入和应用生命周期，不建议在此直接堆业务逻辑。
"""
from __future__ import annotations

import secrets
from datetime import timedelta
from pathlib import Path

from flask import Flask, session

from .auth import AuthStore
from .cards import CardRegistry, QuarkStorageCard
from .cards_metadata import DoubanMetadataCard
from .clients.douban import DoubanClient
from .clients.http import HttpClient
from .clients.telegram import TelegramClient
from .config_store import ConfigStore
from .logging_setup import configure_logging, recent_logs
from .services.metadata import MetadataProviderManager
from .services.notifications import NotificationManager
from .services.resource_sources import ResourceSourceManager
from .services.search import SearchService
from .services.storage_targets import StorageTargetManager
from .services.subscriptions import SubscriptionManager
from .services.tasks import TaskManager
from .settings import PROJECT_ROOT, load_settings
from .web import LoginRateLimiter, register_web


def create_app(
    test_config: dict | None = None,
    *,
    start_scheduler: bool = True,
) -> Flask:
    settings = load_settings()

    if test_config and "MOVIESYNC_DATA_DIR" in test_config:
        settings = settings.__class__(
            data_dir=Path(
                test_config["MOVIESYNC_DATA_DIR"]
            ).resolve(),
            host=settings.host,
            port=settings.port,
            secret_key=test_config.get(
                "SECRET_KEY",
                settings.secret_key,
            ),
            cookie_secure=False,
            debug=True,
        )

        settings.data_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

    logger = configure_logging(settings.log_dir)

    auth = AuthStore(
        settings.auth_file,
        PROJECT_ROOT / "auth.json",
    )

    config_store = ConfigStore(
        settings.config_file,
        PROJECT_ROOT,
    )

    douban = DoubanClient()
    telegram = TelegramClient()
    card_registry = CardRegistry()
    resource_sources = ResourceSourceManager(
        telegram,
        config_store,
        logger,
        registry=card_registry,
    )
    resource_sources.load_plugins({
        "telegram": telegram,
        "config_store": config_store,
        "logger": logger,
    })
    card_registry.register(QuarkStorageCard(config_store))
    card_registry.register(DoubanMetadataCard(douban))
    metadata = MetadataProviderManager(card_registry, logger, config_store=config_store)
    metadata.load_plugins({
        "config_store": config_store,
        "logger": logger,
    })
    storage_targets = StorageTargetManager(
        card_registry,
        config_store,
        logger,
    )
    storage_targets.load_plugins({
        "config_store": config_store,
        "logger": logger,
    })
    notifications = NotificationManager(card_registry, logger, config_store=config_store)
    notifications.load_plugins({
        "config_store": config_store,
        "logger": logger,
    })

    http = HttpClient()

    tasks = TaskManager(
        settings.data_dir / "tasks.json",
        logger,
    )

    subscriptions = SubscriptionManager(
        settings.subscriptions_file,
        storage_targets,
        resource_sources,
        logger,
    )

    search_service = SearchService(
        resource_sources,
        storage_targets,
        logger,
    )

    services = {
        "logger": logger,
        "logs": recent_logs,
        "auth": auth,
        "config": config_store,
        "douban": douban,
        "metadata": metadata,
        "notifications": notifications,
        "telegram": telegram,
        "resource_sources": resource_sources,
        "card_registry": card_registry,
        "storage_targets": storage_targets,
        "http": http,
        "subscriptions": subscriptions,
        "tasks": tasks,
        "search": search_service,
        "csrf": lambda: secrets.token_urlsafe(32),
        "login_limiter": LoginRateLimiter(),
        "scheduler_enabled": bool(start_scheduler),
    }

    app = Flask(
        __name__,
        template_folder=str(
            PROJECT_ROOT / "templates"
        ),
        static_folder=str(
            PROJECT_ROOT / "static"
        ),
    )

    app.secret_key = settings.secret_key

    app.config.update(
        MAX_CONTENT_LENGTH=1 * 1024 * 1024,

        SESSION_COOKIE_NAME="moviesync_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=settings.cookie_secure,

        # 登录有效期 24 小时。
        # 有请求时自动续期。
        PERMANENT_SESSION_LIFETIME=timedelta(hours=24),
        SESSION_REFRESH_EACH_REQUEST=True,

        JSON_SORT_KEYS=False,
    )

    app.extensions["moviesync"] = services
    app.extensions["moviesync_settings"] = settings

    @app.context_processor
    def inject_csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)

        return {
            "csrf_token": session["csrf_token"]
        }

    register_web(app, services)

    if start_scheduler and not app.testing:
        subscriptions.start_scheduler()

    return app
