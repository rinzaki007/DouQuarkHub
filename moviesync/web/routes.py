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


@api.post("/check-cookie")
@require_csrf
def check_cookie():
    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    cookie = (
        str(
            data.get("cookie")
            or ""
        ).strip()
        or _services()[
            "config"
        ].get_cookie()
    )

    valid = (
        _services()["quark_factory"](
            cookie
        ).check_cookie_valid()
        if cookie
        else False
    )

    return jsonify(
        {
            "valid": valid,
            "message": (
                "Cookie 有效"
                if valid
                else "Cookie 已失效或未配置"
            ),
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


@api.post("/storage-targets/default")
@require_csrf
def set_default_storage_target():
    data = request.get_json(silent=True) or {}
    target_id = str(data.get("target_id") or "").strip()
    try:
        saved = _services()["config"].set_default_storage_target_id(target_id)
    except ValueError as exc:
        return _json_error(str(exc))
    if saved and not _services()["storage_targets"].get(saved):
        return _json_error("指定的存储目标未加载或已停用")
    return jsonify({"success": True, "default_target_id": saved})


@api.get("/cards")
def cards():
    """返回当前进程已加载的卡片 Manifest。动态安装暂未开放。"""
    registry = _services()["card_registry"]
    return jsonify(
        {
            "success": True,
            "cards": registry.manifests(),
            "dynamic_install_enabled": False,
        }
    )


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
    try:
        saved = _services()["config"].save_quark_config(data)
    except ValueError as exc:
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
            "health": config.get("health", {}),
        },
    })


@api.post("/cards/telegram/config")
@require_csrf
def save_telegram_card_config():
    data = request.get_json(silent=True) or {}
    try:
        saved = _services()["config"].save_telegram_config(data)
    except ValueError as exc:
        return _json_error(str(exc))
    return jsonify({
        "success": True,
        "enabled": bool(saved.get("enabled", True)),
        "config": saved.get("config", {}),
        "message": "Telegram 卡片配置已保存",
    })


@api.post("/cards/quark/check")
@require_csrf
def check_quark_card():
    card = _services()["card_registry"].get("quark")
    if not card:
        return _json_error("Quark 卡片未加载", 404)
    result = card.check({})
    return jsonify({"success": True, **result})

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
        movies = _services()[
            "douban"
        ].get_movies(
            tag,
            sort_type,
        )

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
                "movies": _services()[
                    "douban"
                ].search(query),
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

        candidates_map[
            title
        ] = service.search_movie_candidates(
            movie,
            config.load(),
        )

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

    config_store = _services()["config"]
    try:
        target_fid = _normalize_fid(
            data.get("target_fid")
            or config_store.get_default_storage_target_id()
            or "0"
        )
    except ValueError as exc:
        return _json_error(str(exc))

    payload = {
        "movie": movie,
        "candidate": candidate,
        "target_fid": target_fid,
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
                _services()["config"].get_quark_config().get("category_fids", {}),
                progress,
            )

    task = _services()["tasks"].create_transfer_task(payload, runner)
    return jsonify({
        "success": True,
        "task": {key: value for key, value in task.items() if key != "retry_payload"},
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
        items.append({
            "id": "subscription:" + str(sub.get("id")),
            "type": "subscription",
            "kind": "智能追剧",
            "title": sub.get("title", "未命名任务"),
            "status": "error" if sub.get("last_error") else (
                "pending" if sub.get("pending_save_keys") else "waiting"
            ),
            "progress": 100,
            "total": len(sub.get("files", []) or []),
            "success_count": len(sub.get("saved_episodes", []) or []),
            "skipped_count": 0,
            "failed_count": 1 if sub.get("last_error") else 0,
            "message": sub.get("last_error") or sub.get("last_check", "等待检查"),
            "next_run_at": sub.get("next_run_at"),
            "updated_at": sub.get("last_check_at") or 0,
            "run_history": history[-10:],
            "subscription_id": sub.get("id"),
            "retry_count": sub.get("retry_count", 0),
            "pending_save_keys": sub.get("pending_save_keys", []) or [],
            "phase": "pending" if sub.get("pending_save_keys") else "waiting",
            "phase_label": "等待夸克确认" if sub.get("pending_save_keys") else "等待下次检查",
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
        task = {
            "id": "subscription:" + sub_id,
            "type": "subscription",
            "kind": "智能追剧",
            "title": sub.get("title", "未命名任务"),
            "status": "failed" if sub.get("last_error") else ("pending" if sub.get("pending_save_keys") else "waiting"),
            "phase": "pending" if sub.get("pending_save_keys") else "waiting",
            "phase_label": "等待夸克确认" if sub.get("pending_save_keys") else "等待下次检查",
            "progress": 100,
            "total": len(sub.get("files", []) or []),
            "success_count": len(sub.get("saved_episodes", []) or []),
            "skipped_count": 0,
            "failed_count": 1 if sub.get("last_error") else 0,
            "message": sub.get("last_error") or sub.get("last_check", "等待检查"),
            "next_run_at": sub.get("next_run_at"),
            "updated_at": sub.get("last_check_at") or 0,
            "run_history": (sub.get("run_history", []) or [])[-20:],
            "subscription_id": sub_id,
            "pending_save_keys": sub.get("pending_save_keys", []) or [],
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
                payload.get("target_fid")
                or _services()["config"].get_default_storage_target_id() or "0",
                _services()["config"].get_quark_config().get("category_fids", {}),
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
            target_fid = _normalize_fid(
                data.get(
                    "target_fid"
                )
                or _services()[
                    "config"
                ].get_quark_config().get(
                    "default_fid",
                    "0",
                )
            )

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
                files=data.get(
                    "files",
                    [],
                ),
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
