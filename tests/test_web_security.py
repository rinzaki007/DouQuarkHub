"""Web 安全回归测试。

覆盖：初始化/登录前置保护、未登录 API 拦截、CSRF 强制校验以及账号初始化状态切换。
"""
from moviesync.app import create_app


def make_app(tmp_path):
    return create_app(
        {"MOVIESYNC_DATA_DIR": str(tmp_path)},
        start_scheduler=False,
    )


def test_uninitialized_requests_are_redirected_or_rejected(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"] == "/setup"

    response = client.get("/api/config")
    assert response.status_code == 401
    assert response.get_json()["need_setup"] is True

    response = client.get("/healthz")
    assert response.status_code == 200


def test_setup_login_and_csrf_protection(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    response = client.post(
        "/api/setup",
        json={"username": "admin", "password": "password123"},
    )
    assert response.status_code == 200
    assert response.get_json()["success"] is True

    response = client.get("/api/config")
    assert response.status_code == 200

    with client.session_transaction() as session:
        csrf_token = session["csrf_token"]

    response = client.post(
        "/api/config",
        json={"default_fid": "abc123"},
    )
    assert response.status_code == 403

    response = client.post(
        "/api/config",
        json={"default_fid": "abc123"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 200

    fresh_client = app.test_client()
    response = fresh_client.get("/api/config")
    assert response.status_code == 401
    assert response.get_json()["need_login"] is True


def test_setup_is_closed_after_initialization(tmp_path):
    app = make_app(tmp_path)
    client = app.test_client()

    client.post(
        "/api/setup",
        json={"username": "admin", "password": "password123"},
    )

    response = client.post(
        "/api/setup",
        json={"username": "attacker", "password": "password123"},
    )
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"
