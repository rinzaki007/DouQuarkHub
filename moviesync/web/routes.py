from __future__ import annotations

from functools import wraps
from urllib.parse import urlparse

from flask import Blueprint, Response, current_app, jsonify, redirect, render_template, request, session


pages = Blueprint("pages", __name__)
api = Blueprint("api", __name__, url_prefix="/api")


def _services():
    return current_app.extensions["moviesync"]


def _json_error(message: str, status: int = 400):
    return jsonify({"success": False, "message": message}), status


def require_csrf(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if request.method in {
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
        }:
            expected = session.get("csrf_token")

            supplied = (
                request.headers.get("X-CSRF-Token")
                or request.form.get("csrf_token")
            )

            if not expected or not secrets.compare_digest(
                str(expected),
                str(supplied or ""),
            ):
                return _json_error(
                    "CSRF 校验失败",
                    403,
                )

        return view(*args, **kwargs)

    return wrapped


@pages.get("/")
def index():
    return render_template("index.html")


@pages.get("/admin")
def admin():
    return render_template("admin.html")


@pages.get("/setup")
def setup_page():
    return render_template("login.html", is_setup=True)


@pages.get("/login")
def login_page():
    return render_template("login.html", is_setup=False)


@pages.post("/logout")
@require_csrf
def logout():
    session.clear()
    return redirect("/login")


@pages.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@pages.get("/openlist")
def openlist():
    return redirect(_services()["config"].load().get("openlist_url"))


@api.post("/setup")
def setup():
    data = request.get_json(silent=True) or {}
    try:
        _services()["auth"].setup(str(data.get("username", "")), str(data.get("password", "")))
    except ValueError as exc:
        return _json_error(str(exc))
    session.clear()
    session.permanent = True
    session["logged_in"] = True
    session["username"] = str(data.get("username", "")).strip()
    session["csrf_token"] = _services()["csrf"]()
    _services()["logger"].info("管理员完成系统初始化")
    return jsonify({"success": True, "message": "管理员账号创建成功！"})


@api.post("/login")
def login():
    services = _services()
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
    remote_addr = request.remote_addr or "unknown"
    allowed, retry_after = services["login_limiter"].allow(remote_addr)
    if not allowed:
        return jsonify({"success": False, "message": f"尝试次数过多，请 {retry_after} 秒后再试"}), 429
    if not services["auth"].verify(username, password):
        services["login_limiter"].record_failure(remote_addr)
        return _json_error("用户名或密码错误", 401)
    services["login_limiter"].record_success(remote_addr)
    session.clear()
    session.permanent = True
    session["logged_in"] = True
    session["username"] = username
    session["csrf_token"] = services["csrf"]()
    services["logger"].info("管理员登录成功: %s", username)
    return jsonify({"success": True, "message": "登录成功"})


@api.get("/csrf")
def csrf():
    return jsonify({"token": session.get("csrf_token")})


@api.get("/config")
def get_config():
    return jsonify({"success": True, "config": _services()["config"].public()})


@api.post("/config")
@require_csrf
def save_config():
    data = request.get_json(silent=True) or {}
    try:
        _services()["config"].save(data)
    except ValueError as exc:
        return _json_error(str(exc))
    _services()["logger"].info("系统配置已更新")
    return jsonify({"success": True, "message": "配置已保存"})


@api.route("/channels", methods=["GET", "POST"])
@require_csrf
def channels():
    config = _services()["config"]
    if request.method == "GET":
        return jsonify({"success": True, "channels": config.get_channels()})
    data = request.get_json(silent=True) or {}
    try:
        saved = config.save_channels(data.get("channels", []))
    except ValueError as exc:
        return _json_error(str(exc))
    return jsonify({"success": True, "channels": saved})


@api.get("/admin/logs")
def admin_logs():
    return jsonify({"success": True, "logs": _services()["logs"]()})


@api.post("/check-cookie")
@require_csrf
def check_cookie():
    data = request.get_json(silent=True) or {}
    cookie = str(data.get("cookie") or "").strip() or _services()["config"].get_cookie()
    valid = _services()["quark_factory"](cookie).check_cookie_valid() if cookie else False
    return jsonify({"valid": valid, "message": "Cookie 有效" if valid else "Cookie 已失效或未配置"})


@api.get("/check-channels")
def check_channels_health():
    channels = _services()["config"].get_channels()
    telegram = _services()["telegram"]
    results = []
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(channels)))) as executor:
        results = list(executor.map(telegram.check_channel, channels)) if channels else []
    valid_count = sum(bool(item) for item in results)
    return jsonify({"success": True, "total": len(channels), "valid_count": valid_count})


@api.get("/get-movies")
def get_movies():
    tag = request.args.get("tag", "电影")
    sort_type = request.args.get("sort", "U")
    try:
        movies = _services()["douban"].get_movies(tag, sort_type)
        return jsonify({"success": True, "movies": movies})
    except Exception as exc:
        _services()["logger"].exception("获取豆瓣影片失败")
        return jsonify({"success": False, "movies": [], "message": str(exc)})


@api.get("/search-douban")
def search_douban():
    query = request.args.get("q", "").strip()[:80]
    if not query:
        return jsonify({"success": False, "movies": []})
    try:
        return jsonify({"success": True, "movies": _services()["douban"].search(query)})
    except Exception as exc:
        _services()["logger"].warning("豆瓣搜索失败: %s", exc)
        return jsonify({"success": False, "movies": [], "message": "豆瓣搜索失败"})


@api.post("/search-candidates")
@require_csrf
def search_candidates():
    data = request.get_json(silent=True) or {}
    movies = data.get("movies", [])
    config = _services()["config"]
    cookie = config.get_cookie()
    if not movies:
        return _json_error("未选择影片")
    if not cookie:
        return _json_error("未配置夸克 Cookie")
    if not isinstance(movies, list) or len(movies) > 10:
        return _json_error("一次最多检索 10 部影片")

    service = _services()["search_factory"](cookie)
    candidates_map = {}
    for movie in movies:
        title = movie.get("title", str(movie)) if isinstance(movie, dict) else str(movie)
        candidates_map[title] = service.search_movie_candidates(movie, config.get_channels())
    return jsonify({"success": True, "candidates_map": candidates_map})


@api.post("/transfer-selected")
@require_csrf
def transfer_selected():
    data = request.get_json(silent=True) or {}
    movie = data.get("movie")
    candidate = data.get("candidate")
    if not isinstance(movie, dict) or not isinstance(candidate, dict):
        return _json_error("参数不完整")
    cookie = _services()["config"].get_cookie()
    if not cookie:
        return _json_error("未配置夸克 Cookie")

    config = _services()["config"].load()
    target_fid = str(data.get("target_fid") or config.get("default_fid", "0"))
    category_fids = {} if data.get("target_fid") else config.get("category_fids", {})
    success, message = _services()["search_factory"](cookie).transfer_selected_resource(movie, candidate, target_fid, category_fids)
    return jsonify({"success": success, "message": message})


@api.route("/subscriptions", methods=["GET", "POST", "DELETE"])
@require_csrf
def subscriptions():
    manager = _services()["subscriptions"]
    if request.method == "GET":
        return jsonify({"success": True, "subscriptions": manager.get_subscriptions()})
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        try:
            sub = manager.add_subscription(
                title=data.get("title"),
                pwd_id=data.get("pwd_id"),
                target_fid=data.get("target_fid") or _services()["config"].load().get("default_fid", "0"),
                interval_hours=int(data.get("interval_hours", 6)),
                start_ep=int(data.get("start_ep", 0)),
                channel=data.get("channel", ""),
                files=data.get("files", []),
            )
        except (TypeError, ValueError) as exc:
            return _json_error(str(exc))
        return jsonify({"success": True, "subscription": sub, "message": "智能追剧任务添加成功！"})

    sub_id = request.args.get("id") or str((request.get_json(silent=True) or {}).get("id") or "")
    if not sub_id:
        return _json_error("未提供订阅 ID")
    if not manager.delete_subscription(sub_id):
        return _json_error("未找到订阅任务", 404)
    return jsonify({"success": True, "message": "已删除订阅"})


@api.post("/subscriptions/run-now")
@require_csrf
def run_subscription_now():
    sub_id = str((request.get_json(silent=True) or {}).get("id") or "")
    if not sub_id:
        return _json_error("未提供订阅 ID")
    success, message = _services()["subscriptions"].check_subscription_now(sub_id)
    return jsonify({"success": success, "message": message})


@api.get("/proxy-img")
def proxy_img():
    target = request.args.get("url", "").strip()
    parsed = urlparse(target)
    if parsed.scheme != "https" or not parsed.hostname:
        return Response("Invalid URL", status=400)

    host = parsed.hostname.lower()
    if not (host.endswith(".doubanio.com") or host == "doubanio.com"):
        return Response("Host not allowed", status=403)

    try:
        response = _services()["http"].session.get(
            target,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
                "Referer": "https://movie.douban.com/",
            },
            timeout=8,
            stream=True,
        )

        if response.status_code != 200:
            return Response("Image unavailable", status=404)

        content_type = response.headers.get(
            "Content-Type", "image/jpeg"
        ).split(";", 1)[0]

        if not content_type.startswith("image/"):
            return Response("Not an image", status=415)

        return Response(response.content, mimetype=content_type)

    except Exception:
        return Response("Image unavailable", status=404)


@api.post("/change-password")
@require_csrf
def change_password():
    data = request.get_json(silent=True) or {}

    current_password = str(
        data.get("current_password") or ""
    )

    new_password = str(
        data.get("new_password") or ""
    )

    username = str(
        session.get("username") or ""
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
        return _json_error(str(exc))

    _services()["logger"].info(
        "管理员修改密码成功: %s",
        username,
    )

    session.clear()

    return jsonify(
        {
            "success": True,
            "message": "密码修改成功，请重新登录",
        }
    )
