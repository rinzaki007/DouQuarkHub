"""MovieSync Flask 页面与 API 路由。

用途：提供首页、登录/初始化、后台配置、豆瓣数据、资源检索/转存、自动追剧和图片代理等 HTTP 接口。
维护说明：修改数据的 API 使用 CSRF 校验；FID 会在路由层先校验，再交给业务服务继续处理。
"""
from __future__ import annotations

import secrets
from functools import wraps
from urllib.parse import urlparse

from flask import (
    Blueprint,
    Response,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
)

pages = Blueprint("pages", __name__)
api = Blueprint("api", __name__, url_prefix="/api")


def _services():
    return current_app.extensions["moviesync"]


def _json_error(message: str, status: int = 400):
    return jsonify(
        {
            "success": False,
            "message": message,
        }
    ), status


def _normalize_fid(
    value: object,
    default: str = "0",
) -> str:
    fid = str(
        value or default
    ).strip()

    if not fid:
        fid = default

    if len(fid) > 128:
        raise ValueError(
            "目标存储目录 FID 不能超过 128 个字符"
        )

    if not all(
        char.isalnum() or char in "_-"
        for char in fid
    ):
        raise ValueError(
            "目标存储目录 FID 格式无效"
        )

    return fid


def _subscription_task_state(sub: dict) -> dict:
    status = str(sub.get("status") or "").strip()
    if not status:
        status = "error" if sub.get("last_error") else (
            "pending" if sub.get("pending_save_keys") else "waiting"
        )

    phase = str(sub.get("phase") or "").strip()
    if not phase:
        phase = "pending" if sub.get("pending_save_keys") else "waiting"

    phase_label = str(sub.get("phase_label") or "").strip()
    if not phase_label:
        phase_label = (
            "等待存储目标确认"
            if sub.get("pending_save_keys")
            else "等待下次检查"
        )

    return {
        "status": status,
        "phase": phase,
        "phase_label": phase_label,
        "progress": 100 if status == "success" else 0,
    }


def require_csrf(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if request.method in {
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
        }:
            expected = session.get(
                "csrf_token"
            )

            supplied = (
                request.headers.get(
                    "X-CSRF-Token"
                )
                or request.form.get(
                    "csrf_token"
                )
            )

            if (
                not expected
                or not secrets.compare_digest(
                    str(expected),
                    str(supplied or ""),
                )
            ):
                return _json_error(
                    "CSRF 校验失败",
                    403,
                )

        return view(*args, **kwargs)

    return wrapped


@pages.get("/")
def index():
    return render_template(
        "index.html"
    )


@pages.get("/tasks")
def tasks():
    return render_template(
        "tasks.html"
    )

@pages.get("/resource-select")
def resource_select():
    return render_template(
        "resource_select.html"
    )


@pages.get("/favicon.ico")
def favicon():
    return Response(status=204)


@pages.get("/admin")
def admin():
    return render_template(
        "admin.html"
    )


@pages.get("/setup")
def setup_page():
    return render_template(
        "login.html",
        is_setup=True,
    )


@pages.get("/login")
def login_page():
    return render_template(
        "login.html",
        is_setup=False,
    )


@pages.post("/logout")
@require_csrf
def logout():
    session.clear()
    return redirect("/login")


@pages.get("/healthz")
def healthz():
    services = _services()
    scheduler = services.get("subscriptions")

    scheduler_alive = bool(
        scheduler
        and scheduler.worker
        and scheduler.worker.is_alive()
    )

    scheduler_expected = bool(
        services.get("scheduler_enabled")
    )

    if scheduler_expected and not scheduler_alive:
        return jsonify(
            {
                "status": "degraded",
                "scheduler": "stopped",
            }
        ), 503

    return jsonify(
        {
            "status": "ok",
            "scheduler": (
                "running"
                if scheduler_alive
                else "disabled"
            ),
        }
    )


@pages.get("/openlist")
def openlist():
    url = str(_services()["config"].load().get("openlist_url") or "").strip()
    return redirect(url or "/")


@api.post("/setup")
def setup():
    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    username = str(
        data.get("username", "")
    )

    password = str(
        data.get("password", "")
    )

    try:
        _services()["auth"].setup(
            username,
            password,
        )

    except ValueError as exc:
        return _json_error(
            str(exc)
        )

    session.clear()
    session.permanent = True
    session["logged_in"] = True
    session["username"] = username.strip()
    session["csrf_token"] = (
        _services()["csrf"]()
    )

    _services()["logger"].info(
        "管理员完成系统初始化"
    )

    return jsonify(
        {
            "success": True,
            "message": "管理员账号创建成功！",
        }
    )


@api.post("/login")
def login():
    services = _services()

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    username = str(
        data.get("username", "")
    ).strip()

    password = str(
        data.get("password", "")
    )

    remote_addr = (
        request.remote_addr
        or "unknown"
    )

    allowed, retry_after = (
        services["login_limiter"].allow(
            remote_addr
        )
    )

    if not allowed:
        return jsonify(
            {
                "success": False,
                "message": (
                    f"尝试次数过多，请 "
                    f"{retry_after} 秒后再试"
                ),
            }
        ), 429

    if not services["auth"].verify(
        username,
        password,
    ):
        services[
            "login_limiter"
        ].record_failure(
            remote_addr
        )

        return _json_error(
            "用户名或密码错误",
            401,
        )

    services[
        "login_limiter"
    ].record_success(
        remote_addr
    )

    session.clear()
    session.permanent = True
    session["logged_in"] = True
    session["username"] = username
    session["csrf_token"] = (
        services["csrf"]()
    )

    services["logger"].info(
        "管理员登录成功: %s",
        username,
    )

    return jsonify(
        {
            "success": True,
            "message": "登录成功",
        }
    )


@api.get("/csrf")
def csrf():
    return jsonify(
        {
            "token": session.get(
                "csrf_token"
            )
        }
    )


@api.get("/config")
def get_config():
    return jsonify(
        {
            "success": True,
            "config": _services()[
                "config"
            ].public(),
        }
    )


@api.get("/config/export")
def export_config():
    return jsonify(
        {
            "success": True,
            "config": _services()["config"].load(),
        }
    )


@api.post("/config")
@require_csrf
def save_config():
    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    try:
        _services()["config"].save(
            data
        )

    except ValueError as exc:
        return _json_error(
            str(exc)
        )

    _services()["logger"].info(
        "系统配置已更新"
    )

    return jsonify(
        {
            "success": True,
            "message": "配置已保存",
        }
    )


@api.route(
    "/channels",
    methods=["GET", "POST"],
)
@require_csrf
def channels():
    config = _services()["config"]

    if request.method == "GET":
        return jsonify(
            {
                "success": True,
                "channels": (
                    config.get_channels()
                ),
            }
        )

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    try:
        saved = config.save_channels(
            data.get(
                "channels",
                [],
            )
        )

    except ValueError as exc:
        return _json_error(
            str(exc)
        )

    return jsonify(
        {
            "success": True,
            "channels": saved,
        }
    )


@api.get("/admin/logs")
def admin_logs():
    return jsonify(
        {
            "success": True,
            "logs": _services()[
                "logs"
            ](),
        }
    )


@api.get("/check-channels")
def check_channels_health():
    results = _services()["resource_sources"].check_all()
    telegram = next(
        (item for item in results if item.get("id") == "telegram"),
        {"total": 0, "valid_count": 0},
    )
    return jsonify(
        {
            "success": True,
            "total": telegram.get("total", 0),
            "valid_count": telegram.get("valid_count", 0),
            "resource_sources": results,
        }
    )


@api.get("/resource-sources")
def resource_sources_health():
    return jsonify(
        {
            "success": True,
            "resource_sources": _services()["resource_sources"].get_status(),
        }
    )


@api.get("/storage-targets")
def storage_targets():
    manager = _services()["storage_targets"]
    return jsonify({
        "success": True,
        "targets": manager.list_targets(),
        "default_target_id": _services()["config"].get_default_storage_target_id(),
    })

@api.get("/storage-targets/<target_id>/destinations")
def storage_target_destinations(target_id):
    manager = _services()["storage_targets"]
    if not manager.get(target_id):
        return _json_error("指定的存储目标未加载或已停用", 404)
    return jsonify({
        "success": True,
        "target_id": target_id,
        "destinations": manager.destination_options(target_id),
    })



@api.post("/storage-targets/default")
@require_csrf
def set_default_storage_target():
    data = request.get_json(silent=True) or {}
    target_id = str(data.get("target_id") or "").strip()
    if target_id and not _services()["storage_targets"].get(target_id):
        return _json_error("指定的存储目标未加载或已停用")
    try:
        saved = _services()["config"].set_default_storage_target_id(target_id)
    except ValueError as exc:
        return _json_error(str(exc))
    return jsonify({"success": True, "default_target_id": saved})


@api.get("/cards")
def cards():
    """返回当前进程已加载的卡片 Manifest。动态安装暂未开放。"""
    registry = _services()["card_registry"]
    config_store = _services()["config"]
    config = config_store.load()
    card_configs = config.get("cards") if isinstance(config, dict) else {}
    cards = []
    for card in registry.list():
        saved = card_configs.get(card.card_id) if isinstance(card_configs, dict) else {}
        saved = saved if isinstance(saved, dict) else {}
        item = card.manifest.to_dict()
        item["enabled"] = bool(saved.get("enabled", True))
        card_config = saved.get("config", {})
        item["configured"] = False
        if card.card_id == "telegram":
            health = card_config.get("health", {}) if isinstance(card_config, dict) else {}
            item["configured"] = bool(card_config.get("channels"))
            item["health"] = health or {
                "status": "idle",
                "message": "尚未检查",
            }
        elif card.card_id == "quark":
            has_cookie = bool(card_config.get("cookie")) if isinstance(card_config, dict) else False
            item["configured"] = has_cookie
            item["health"] = {
                "status": "configured" if has_cookie else "unconfigured",
                "message": "Cookie 已配置，可检查连接状态" if has_cookie else "尚未配置夸克 Cookie",
            }
        else:
            try:
                item["health"] = card.check(card_config)
                item["configured"] = (
                    item["health"].get("status") not in {"unconfigured", "idle"}
                    if isinstance(item["health"], dict)
                    else True
                )
            except Exception as exc:
                item["health"] = {
                    "status": "unavailable",
                    "message": f"卡片检查失败: {exc}",
                }
        cards.append(item)
    return jsonify(
        {
            "success": True,
            "cards": cards,
            "dynamic_install_enabled": False,
        }
    )


def _card_config_view(card, raw_config):
    """仅向管理界面返回 Manifest 声明的字段，并对敏感值做脱敏。"""
    raw_config = raw_config if isinstance(raw_config, dict) else {}
    public_config, has_value, fields = {}, {}, []
    sensitive_markers = ("cookie", "token", "secret", "password", "api_key", "authorization", "credential")
    for declared in card.manifest.config_fields:
        field = dict(declared)
        key = str(field.get("key") or "")
        secret = bool(field.get("secret")) or any(marker in key.lower() for marker in sensitive_markers)
        field["secret"] = secret
        value = raw_config.get(key, field.get("default", {} if field.get("type") == "json" else ""))
        if secret:
            public_config[key] = ""
            has_value[key] = bool(value)
        else:
            public_config[key] = value
        fields.append(field)
    return fields, public_config, has_value


@api.route("/cards/<card_id>/config", methods=["GET", "POST"])
@require_csrf
def resource_card_config(card_id):
    """所有已注册卡片共用的配置接口；字段由 CardManifest 声明。"""
    card = _services()["card_registry"].get(card_id)
    if card is None:
        return _json_error("卡片未加载", 404)

    config_store = _services()["config"]
    cards_config = config_store.load().get("cards", {})
    saved = cards_config.get(card_id, {}) if isinstance(cards_config, dict) else {}
    saved = saved if isinstance(saved, dict) else {}
    raw_config = saved.get("config", {})
    raw_config = raw_config if isinstance(saved.get("config", {}), dict) else {}

    if request.method == "GET":
        fields, public_config, has_value = _card_config_view(card, raw_config)
        return jsonify({"success": True, "card_id": card_id, "enabled": bool(saved.get("enabled", True)),
                        "fields": fields, "config": public_config, "has_value": has_value})

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _json_error("请求内容必须是 JSON 对象")
    incoming = data.get("config", {})
    if not isinstance(incoming, dict):
        return _json_error("config 必须是 JSON 对象")
    fields_by_key = {str(field.get("key")): field for field in card.manifest.config_fields}
    unknown = set(incoming) - set(fields_by_key)
    if unknown:
        return _json_error("包含未声明的配置字段: " + ", ".join(sorted(unknown)))

    merged, persisted_incoming = dict(raw_config), {}
    sensitive_markers = ("cookie", "token", "secret", "password", "api_key", "authorization", "credential")
    for key, value in incoming.items():
        field = fields_by_key[key]
        field_type = field.get("type", "string")
        secret = bool(field.get("secret")) or any(marker in key.lower() for marker in sensitive_markers)
        if secret and value in (None, ""):
            continue
        if field_type == "json" and not isinstance(value, (dict, list)):
            return _json_error(f"配置字段「{field.get('label') or key}」必须是 JSON 对象或数组")
        if field_type == "boolean" and not isinstance(value, bool):
            return _json_error(f"配置字段「{field.get('label') or key}」必须是布尔值")
        if field_type == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
            return _json_error(f"配置字段「{field.get('label') or key}」必须是数字")
        if field_type in {"string", "password", "textarea"} and not isinstance(value, str):
            return _json_error(f"配置字段「{field.get('label') or key}」必须是文本")
        merged[key] = value
        persisted_incoming[key] = value

    for key, field in fields_by_key.items():
        secret = bool(field.get("secret")) or any(marker in key.lower() for marker in sensitive_markers)
        if field.get("required") and not merged.get(key) and not (secret and raw_config.get(key)):
            return _json_error(f"请填写必填配置：{field.get('label') or key}")
    enabled = data.get("enabled") if "enabled" in data else None
    if enabled is not None and not isinstance(enabled, bool):
        return _json_error("enabled 必须是布尔值")
    try:
        validated = card.validate_config(merged)
        if not isinstance(validated, dict):
            return _json_error("卡片配置校验必须返回 JSON 对象")
        # 只写入本次声明并提交的字段，使用卡片规范化后的值；其余内部配置保持不变。
        persisted_incoming = {
            key: validated.get(key, value)
            for key, value in persisted_incoming.items()
        }
        saved = config_store.save_card_config(card_id, persisted_incoming, enabled=enabled)
    except (ValueError, TypeError) as exc:
        return _json_error(str(exc))
    fields, public_config, has_value = _card_config_view(card, saved.get("config", {}))
    return jsonify({"success": True, "card_id": card_id, "enabled": bool(saved.get("enabled", True)),
                    "fields": fields, "config": public_config, "has_value": has_value,
                    "message": "卡片配置已保存"})


@api.post("/cards/<card_id>/check")
@require_csrf
def check_card_connection(card_id):
    """调用卡片自身的健康检查；卡片必须声明健康检查能力。"""
    card = _services()["card_registry"].get(card_id)
    if card is None:
        return _json_error("卡片未加载", 404)
    supports_check = any(
        capability.endswith(".health_check") or capability.endswith(".check")
        for capability in card.capabilities
    )
    if not supports_check:
        return _json_error("该卡片未声明连接检查能力", 400)
    cards_config = _services()["config"].load().get("cards", {})
    saved = cards_config.get(card_id, {}) if isinstance(cards_config, dict) else {}
    config = saved.get("config", {}) if isinstance(saved, dict) else {}
    try:
        result = card.check(config if isinstance(config, dict) else {})
    except Exception as exc:
        _services()["logger"].exception("卡片 %s 连接检查失败", card_id)
        return _json_error(f"连接检查失败：{exc}", 502)
    if not isinstance(result, dict):
        return _json_error("卡片检查结果格式无效", 502)
    return jsonify({"success": True, **result})


@api.get("/cards/quark/config")
def get_quark_card_config():
    card = _services()["card_registry"].get("quark")
    if not card:
        return _json_error("Quark 卡片未加载", 404)
    config = _services()["config"].get_quark_config()
    saved = _services()["config"].load()["cards"]["quark"]
    return jsonify({
        "success": True,
        "enabled": bool(saved.get("enabled", True)),
        "config": {
            "default_fid": config.get("default_fid", "0"),
            "category_fids": config.get("category_fids", {}),
            "has_cookie": bool(config.get("cookie")),
        },
    })


@api.post("/cards/quark/config")
@require_csrf
def save_quark_card_config():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return _json_error("Quark 卡片配置必须是 JSON 对象")
    services = _services()
    card = services["card_registry"].get("quark")
    if card is None:
        return _json_error("Quark 卡片未加载", 404)
    config_store = services["config"]
    declared_keys = {str(field.get("key")) for field in card.manifest.config_fields}
    incoming_config = {key: value for key, value in data.items() if key in declared_keys}
    merged_config = {**config_store.get_quark_config(), **incoming_config}
    try:
        validated = card.validate_config(merged_config)
        incoming_config = {key: validated.get(key, value) for key, value in incoming_config.items()}
        saved = config_store.save_quark_config({**data, **incoming_config})
    except (ValueError, TypeError) as exc:
        return _json_error(str(exc))
    return jsonify({
        "success": True,
        "enabled": bool(saved.get("enabled", True)),
        "config": {
            "default_fid": saved["config"].get("default_fid", "0"),
            "category_fids": saved["config"].get("category_fids", {}),
            "has_cookie": bool(saved["config"].get("cookie")),
        },
        "message": "Quark 卡片配置已保存",
    })


@api.get("/cards/telegram/config")
def get_telegram_card_config():
    card = _services()["card_registry"].get("telegram")
    if not card:
        return _json_error("Telegram 卡片未加载", 404)
    saved = _services()["config"].load()["cards"]["telegram"]
    config = _services()["config"].get_telegram_config()
    return jsonify({
        "success": True,
        "enabled": bool(saved.get("enabled", True)),
        "config": {
            "channels": config.get("channels", []),
            "magic_regex": config.get("magic_regex", {}),
            "health": config.get("health", {}),
        },
    })


@api.post("/cards/telegram/config")
@require_csrf
def save_telegram_card_config():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return _json_error("Telegram 卡片配置必须是 JSON 对象")
    services = _services()
    card = services["card_registry"].get("telegram")
    if card is None:
        return _json_error("Telegram 卡片未加载", 404)
    config_store = services["config"]
    declared_keys = {str(field.get("key")) for field in card.manifest.config_fields}
    incoming_config = {key: value for key, value in data.items() if key in declared_keys}
    merged_config = {**config_store.get_telegram_config(), **incoming_config}
    try:
        validated = card.validate_config(merged_config)
        incoming_config = {key: validated.get(key, value) for key, value in incoming_config.items()}
        saved = config_store.save_telegram_config({**data, **incoming_config})
    except (ValueError, TypeError) as exc:
        return _json_error(str(exc))
    return jsonify({
        "success": True,
        "enabled": bool(saved.get("enabled", True)),
        "config": saved.get("config", {}),
        "message": "Telegram 卡片配置已保存",
    })


@api.get("/login-backdrop")
def login_backdrop():
    """登录页专用公开背景接口：只返回少量带海报的影视数据，不暴露任何登录后配置。"""
    try:
        movies = _services()["metadata"].list_movies("电影", "U")
        covers = [
            {
                "title": item.get("title", ""),
                "cover": item.get("cover", ""),
            }
            for item in movies
            if isinstance(item, dict) and item.get("cover")
        ][:12]
        return jsonify({"success": True, "movies": covers})
    except Exception:
        _services()["logger"].exception("获取登录页背景海报失败")
        return jsonify({"success": False, "movies": []})


@api.get("/get-movies")
def get_movies():
    tag = request.args.get(
        "tag",
        "电影",
    )

    sort_type = request.args.get(
        "sort",
        "U",
    )

    try:
        movies = _services()["metadata"].list_movies(tag, sort_type)

        return jsonify(
            {
                "success": True,
                "movies": movies,
            }
        )

    except Exception as exc:
        _services()["logger"].exception(
            "获取豆瓣影片失败"
        )

        return jsonify(
            {
                "success": False,
                "movies": [],
                "message": str(exc),
            }
        )


@api.get("/search-douban")
def search_douban():
    query = request.args.get(
        "q",
        "",
    ).strip()[:80]

    if not query:
        return jsonify(
            {
                "success": False,
                "movies": [],
            }
        )

    try:
        return jsonify(
            {
                "success": True,
                "movies": _services()["metadata"].search(query),
            }
        )

    except Exception:
        _services()["logger"].warning(
            "豆瓣搜索失败"
        )

        return jsonify(
            {
                "success": False,
                "movies": [],
                "message": "豆瓣搜索失败",
            }
        )


@api.post("/search-candidates")
@require_csrf
def search_candidates():
    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    movies = data.get(
        "movies",
        [],
    )

    config = _services()["config"]

    if not movies:
        return _json_error(
            "未选择影片"
        )

    if (
        not isinstance(
            movies,
            list,
        )
        or len(movies) > 10
    ):
        return _json_error(
            "一次最多检索 10 部影片"
        )

    service = _services()["search"]

    candidates_map = {}

    for movie in movies:
        title = (
            movie.get(
                "title",
                str(movie),
            )
            if isinstance(
                movie,
                dict,
            )
            else str(movie)
        )

        try:
            candidates_map[
                title
            ] = service.search_movie_candidates(
                movie,
                config.load(),
            )
        except Exception:
            _services()["logger"].exception("资源检索失败: %s", title)
            return _json_error("资源检索暂时失败，请稍后重试；若持续出现，请查看服务日志", 502)

    source_status = config.get_resource_sources()
    unavailable_sources = [
        item.get("name", item.get("id", "未知来源"))
        for item in source_status
        if item.get("enabled", True)
        and (item.get("health") or {}).get("status") == "unavailable"
    ]

    message = ""
    if not any(candidates_map.values()):
        if unavailable_sources:
            message = (
                "当前没有找到可用资源；资源来源不可用："
                + "、".join(unavailable_sources)
                + "。请先检查资源来源状态。"
            )
        else:
            message = "当前已配置资源来源暂未找到可用候选，可稍后重试。"

    return jsonify(
        {
            "success": True,
            "candidates_map": candidates_map,
            "resource_sources": source_status,
            "message": message,
        }
    )


@api.post("/transfer-selected")
@require_csrf
def transfer_selected():
    data = request.get_json(silent=True) or {}
    movie = data.get("movie")
    candidate = data.get("candidate")
    if not isinstance(movie, dict) or not isinstance(candidate, dict):
        return _json_error("参数不完整")

    try:
        target_fid = _normalize_fid(
            data.get("target_fid") or "0"
        )
    except ValueError as exc:
        return _json_error(str(exc))

    storage_target_id = str(
        data.get("storage_target_id")
        or candidate.get("storage_target_id")
        or ""
    ).strip()
    if storage_target_id and not _services()["storage_targets"].get(storage_target_id):
        return _json_error("指定的存储目标不存在或已停用", 400)

    candidate = {
        **candidate,
        "storage_target_id": storage_target_id,
    }
    payload = {
        "movie": movie,
        "candidate": candidate,
        "target_fid": target_fid,
        "storage_target_id": storage_target_id,
    }

    # 任务在线程池中异步执行，后台线程没有 Flask 的默认请求上下文。
    # 显式捕获真实 Flask App，并在 runner 中建立应用上下文。
    app = current_app._get_current_object()

    def runner(progress):
        with app.app_context():
            service = _services()["search"]
            return service.transfer_selected_resource_with_progress(
                movie,
                candidate,
                target_fid,
                {},
                progress,
            )

    task = _services()["tasks"].create_transfer_task(payload, runner)
    return jsonify({
        "success": True,
        "task": {key: value for key, value in task.items() if key not in {"retry_payload", "dedupe_key"}},
        "message": "转存任务已创建",
    })


@api.get("/tasks")
def get_tasks():
    manager = _services()["tasks"]
    transfer_tasks = manager.list_tasks()
    subscriptions = _services()["subscriptions"].get_subscriptions()
    items = []

    for task in transfer_tasks:
        items.append({
            key: value for key, value in task.items()
            if key != "retry_payload"
        })

    for sub in subscriptions:
        history = sub.get("run_history", []) or []
        task_state = _subscription_task_state(sub)
        items.append({
            "id": "subscription:" + str(sub.get("id")),
            "type": "subscription",
            "kind": "智能追剧",
            "title": sub.get("title", "未命名任务"),
            "status": task_state["status"],
            "progress": task_state["progress"],
            "total": len(sub.get("tracked_file_keys", []) or []),
            "success_count": len(sub.get("saved_episodes", []) or []),
            "skipped_count": 0,
            "failed_count": 1 if sub.get("last_error") else 0,
            "message": sub.get("last_error") or sub.get("last_check", "等待检查"),
            "next_run_at": sub.get("next_run_at"),
            "updated_at": sub.get("last_check_at") or 0,
            "run_history": history[-10:],
            "cover": sub.get("cover", ""),
            "source_channel": sub.get("channel_name") or sub.get("channel", ""),
            "tracked_file_count": len(sub.get("tracked_file_keys", []) or []),
            "subscription_id": sub.get("id"),
            "retry_count": sub.get("retry_count", 0),
            "pending_save_keys": sub.get("pending_save_keys", []) or [],
            "pending_save_uncertain": bool(sub.get("pending_save_uncertain")),
            "phase": task_state["phase"],
            "phase_label": task_state["phase_label"],
        })

    items.sort(key=lambda item: float(item.get("updated_at") or item.get("created_at") or 0), reverse=True)
    return jsonify({"success": True, "tasks": items})


@api.delete("/tasks/<task_id>")
@require_csrf
def delete_task(task_id):
    task_id = str(task_id)
    if task_id.startswith("subscription:"):
        sub_id = task_id.split(":", 1)[1]
        if not _services()["subscriptions"].delete_subscription(sub_id):
            return _json_error("未找到追剧任务", 404)
        return jsonify({"success": True, "message": "追剧任务已删除"})
    ok, message = _services()["tasks"].delete_task(task_id)
    if not ok:
        return _json_error(message, 400 if message != "任务不存在" else 404)
    return jsonify({"success": True, "message": message})


@api.post("/tasks/clear-history")
@require_csrf
def clear_task_history():
    removed_tasks = _services()["tasks"].clear_history()
    removed_runs = _services()["subscriptions"].clear_run_history()
    removed = removed_tasks + removed_runs
    return jsonify({"success": True, "removed": removed, "message": f"已清理 {removed} 条历史记录"})


@api.get("/tasks/<task_id>")
def get_task_detail(task_id):
    if str(task_id).startswith("subscription:"):
        sub_id = str(task_id).split(":", 1)[1]
        sub = next(
            (item for item in _services()["subscriptions"].get_subscriptions()
             if str(item.get("id")) == sub_id),
            None,
        )
        if not sub:
            return _json_error("未找到任务", 404)
        task_state = _subscription_task_state(sub)
        task = {
            "id": "subscription:" + sub_id,
            "type": "subscription",
            "kind": "智能追剧",
            "title": sub.get("title", "未命名任务"),
            "status": task_state["status"],
            "phase": task_state["phase"],
            "phase_label": task_state["phase_label"],
            "progress": task_state["progress"],
            "total": len(sub.get("tracked_file_keys", []) or []),
            "success_count": len(sub.get("saved_episodes", []) or []),
            "skipped_count": 0,
            "failed_count": 1 if sub.get("last_error") else 0,
            "message": sub.get("last_error") or sub.get("last_check", "等待检查"),
            "next_run_at": sub.get("next_run_at"),
            "updated_at": sub.get("last_check_at") or 0,
            "run_history": (sub.get("run_history", []) or [])[-20:],
            "subscription_id": sub_id,
            "pending_save_keys": sub.get("pending_save_keys", []) or [],
            "cover": sub.get("cover", ""),
            "source_channel": sub.get("channel", ""),
            "tracked_file_count": len(sub.get("tracked_file_keys", []) or []),
        }
        return jsonify({"success": True, "task": task})
    task = _services()["tasks"].get_task(task_id)
    if not task:
        return _json_error("未找到任务", 404)
    return jsonify({
        "success": True,
        "task": {key: value for key, value in task.items() if key != "retry_payload"},
    })


@api.post("/tasks/<task_id>/retry")
@require_csrf
def retry_task(task_id):
    manager = _services()["tasks"]
    old = manager.get_task(task_id)
    if not old:
        return _json_error("未找到任务", 404)
    if old.get("type") == "subscription":
        sub_id = old.get("subscription_id")
        ok, message = _services()["subscriptions"].check_subscription_now(str(sub_id or ""))
        return jsonify({"success": ok, "message": message})
    if old.get("type") != "transfer":
        return _json_error("不支持重试的任务类型")

    app = current_app._get_current_object()

    def runner(progress):
        with app.app_context():
            payload = old.get("retry_payload") or {}
            movie = payload.get("movie") or {}
            candidate = payload.get("candidate") or {}
            service = _services()["search"]
            return service.transfer_selected_resource_with_progress(
                movie,
                candidate,
                payload.get("target_fid") or "0",
                {},
                progress,
            )

    task = manager.retry_transfer(task_id, runner)
    if not task:
        return _json_error("任务不存在或无法重试", 400)
    return jsonify({
        "success": True,
        "task": {key: value for key, value in task.items() if key != "retry_payload"},
        "message": "已创建重试任务",
    })


@api.route(
    "/subscriptions",
    methods=[
        "GET",
        "POST",
        "DELETE",
    ],
)
@require_csrf
def subscriptions():
    manager = _services()[
        "subscriptions"
    ]

    if request.method == "GET":
        return jsonify(
            {
                "success": True,
                "subscriptions": (
                    manager.get_subscriptions()
                ),
            }
        )

    if request.method == "POST":
        data = (
            request.get_json(
                silent=True
            )
            or {}
        )

        try:
            target_fid = _normalize_fid(data.get("target_fid") or "0")
            cover = str(data.get("cover") or "").strip()[:1000]
            if not cover:
                try:
                    title_for_cover = str(data.get("title") or "").strip()
                    if title_for_cover:
                        matches = _services()["metadata"].search(title_for_cover)
                        if matches:
                            cover = str(matches[0].get("cover") or "").strip()[:1000]
                except Exception:
                    _services()["logger"].debug("获取追剧任务海报失败", exc_info=True)

            sub = manager.add_subscription(
                title=data.get(
                    "title"
                ),
                pwd_id=data.get(
                    "pwd_id"
                ),
                target_fid=target_fid,
                interval_hours=int(
                    data.get(
                        "interval_hours",
                        6,
                    )
                ),
                start_ep=int(
                    data.get(
                        "start_ep",
                        0,
                    )
                ),
                channel=data.get(
                    "channel",
                    "",
                ),
                channel_name=data.get(
                    "channel_name",
                    "",
                ),
                files=data.get(
                    "files",
                    [],
                ),
                storage_target_id=data.get(
                    "storage_target_id",
                    "",
                ),
                cover=cover,
                source_id=data.get("source_id", ""),


            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            return _json_error(
                str(exc)
            )

        return jsonify(
            {
                "success": True,
                "subscription": sub,
                "message": (
                    "智能追剧任务添加成功！"
                ),
            }
        )

    sub_id = request.args.get(
        "id"
    ) or str(
        (
            request.get_json(
                silent=True
            )
            or {}
        ).get("id")
        or ""
    )

    if not sub_id:
        return _json_error(
            "未提供订阅 ID"
        )

    if not manager.delete_subscription(
        sub_id
    ):
        return _json_error(
            "未找到订阅任务",
            404,
        )

    return jsonify(
        {
            "success": True,
            "message": "已删除订阅",
        }
    )


@api.post("/subscriptions/run-now")
@require_csrf
def run_subscription_now():
    sub_id = str(
        (
            request.get_json(
                silent=True
            )
            or {}
        ).get("id")
        or ""
    )

    if not sub_id:
        return _json_error(
            "未提供订阅 ID"
        )

    success, message = (
        _services()[
            "subscriptions"
        ].check_subscription_now(
            sub_id
        )
    )

    return jsonify(
        {
            "success": success,
            "message": message,
        }
    )


@api.post("/subscriptions/resolve-pending")
@require_csrf
def resolve_pending_subscription():
    data = request.get_json(silent=True) or {}
    sub_id = str(data.get("id") or "").strip()
    action = str(data.get("action") or "").strip()
    if not sub_id:
        return _json_error("未提供订阅 ID")
    if action not in {"saved", "not_saved"}:
        return _json_error("确认操作无效")
    success, message = _services()["subscriptions"].resolve_pending_save(sub_id, action)
    return jsonify({"success": success, "message": message})


@api.get("/proxy-img")
def proxy_img():
    target = request.args.get(
        "url",
        "",
    ).strip()

    parsed = urlparse(target)

    if (
        parsed.scheme != "https"
        or not parsed.hostname
    ):
        return Response(
            "Invalid URL",
            status=400,
        )

    host = parsed.hostname.lower()

    if not (
        host.endswith(
            ".doubanio.com"
        )
        or host == "doubanio.com"
    ):
        return Response(
            "Host not allowed",
            status=403,
        )

    try:
        with _services()[
            "http"
        ].session.get(
            target,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/131.0.0.0 "
                    "Safari/537.36"
                ),
                "Referer": (
                    "https://movie.douban.com/"
                ),
            },
            timeout=(
                3,
                8,
            ),
            stream=True,
        ) as response:

            if response.status_code != 200:
                return Response(
                    "Image unavailable",
                    status=404,
                )

            content_type = (
                response.headers.get(
                    "Content-Type",
                    "image/jpeg",
                ).split(
                    ";",
                    1,
                )[0]
                .strip()
                .lower()
            )

            allowed_image_types = {
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/gif",
                "image/avif",
            }

            if content_type not in allowed_image_types:
                return Response(
                    "Not an image",
                    status=415,
                )

            max_size = 5 * 1024 * 1024

            content_length = (
                response.headers.get(
                    "Content-Length"
                )
            )

            if content_length:
                try:
                    if (
                        int(content_length)
                        > max_size
                    ):
                        return Response(
                            "Image too large",
                            status=413,
                        )

                except ValueError:
                    pass

            content = response.raw.read(
                max_size + 1
            )

            if len(content) > max_size:
                return Response(
                    "Image too large",
                    status=413,
                )

            result = Response(
                content,
                mimetype=content_type,
            )

            result.headers[
                "Cache-Control"
            ] = "public, max-age=86400"

            return result

    except Exception:
        return Response(
            "Image unavailable",
            status=404,
        )


@api.post("/change-username")
@require_csrf
def change_username():
    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    current_password = str(
        data.get(
            "current_password"
        )
        or ""
    )

    new_username = str(
        data.get(
            "new_username"
        )
        or ""
    )

    current_username = str(
        session.get(
            "username"
        )
        or ""
    )

    if not current_username:
        return _json_error(
            "当前会话无效，请重新登录",
            401,
        )

    try:
        _services()["auth"].change_username(
            current_username,
            current_password,
            new_username,
        )

    except ValueError as exc:
        return _json_error(
            str(exc)
        )

    _services()["logger"].info(
        "管理员修改用户名: %s -> %s",
        current_username,
        new_username,
    )

    session.clear()

    return jsonify(
        {
            "success": True,
            "message": (
                "用户名修改成功，请重新登录"
            ),
        }
    )


@api.post("/change-password")
@require_csrf
def change_password():
    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    current_password = str(
        data.get(
            "current_password"
        )
        or ""
    )

    new_password = str(
        data.get(
            "new_password"
        )
        or ""
    )

    username = str(
        session.get(
            "username"
        )
        or ""
    )

    if not username:
        return _json_error(
            "当前会话无效，请重新登录",
            401,
        )

    try:
        _services()["auth"].change_password(
            username,
            current_password,
            new_password,
        )

    except ValueError as exc:
        return _json_error(
            str(exc)
        )

    _services()["logger"].info(
        "管理员修改密码成功: %s",
        username,
    )

    session.clear()

    return jsonify(
        {
            "success": True,
            "message": (
                "密码修改成功，请重新登录"
            ),
        }
    )
