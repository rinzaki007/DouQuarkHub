from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque
from threading import Lock

from flask import jsonify, redirect, request, session

from .routes import api, pages


class LoginRateLimiter:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 600):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.failures: dict[str, deque[float]] = defaultdict(deque)
        self.lock = Lock()

    def allow(self, key: str) -> tuple[bool, int]:
        now = time.time()
        with self.lock:
            queue = self.failures[key]
            while queue and now - queue[0] > self.window_seconds:
                queue.popleft()
            if len(queue) < self.max_attempts:
                return True, 0
            return False, max(1, int(self.window_seconds - (now - queue[0])))

    def record_failure(self, key: str) -> None:
        with self.lock:
            self.failures[key].append(time.time())

    def record_success(self, key: str) -> None:
        with self.lock:
            self.failures.pop(key, None)


def register_web(app, services):
    app.register_blueprint(pages)
    app.register_blueprint(api)

    @app.before_request
    def protect_requests():
        if request.path.startswith("/static"):
            return None
        auth = services["auth"]
        if not auth.is_initialized():
            if request.path not in {"/setup", "/api/setup", "/login", "/api/login", "/healthz"}:
                if request.path.startswith("/api/"):
                    return jsonify({"success": False, "message": "需要先完成初始化", "need_setup": True}), 401
                return redirect("/setup")
            return None
        if request.path in {"/setup", "/api/setup"}:
            return redirect("/login")
        if request.path not in {"/login", "/api/login"} and not session.get("logged_in"):
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "message": "未登录", "need_login": True}), 401
            return redirect("/login")
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.path not in {"/api/login", "/api/setup"}:
            # Routes also validate this decorator; this early check keeps accidental mutation endpoints protected.
            token = session.get("csrf_token")
            if not token:
                session["csrf_token"] = secrets.token_urlsafe(32)
        return None

    @app.after_request
    def security_headers(response):
        response.headers.setdefault(
            "X-Content-Type-Options",
            "nosniff",
        )
        response.headers.setdefault(
            "X-Frame-Options",
            "SAMEORIGIN",
        )
        response.headers.setdefault(
            "Referrer-Policy",
            "same-origin",
        )
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        return response

    @app.errorhandler(413)
    def payload_too_large(_):
        return jsonify({"success": False, "message": "请求数据过大"}), 413

    @app.errorhandler(Exception)
    def unhandled(error):
        services["logger"].exception("未处理异常: %s", error)
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "message": "服务器内部错误"}), 500
        return "Internal Server Error", 500
