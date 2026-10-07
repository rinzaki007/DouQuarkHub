```python
@api.post("/change-username")
@require_csrf
def change_username():
    data = request.get_json(
        silent=True
    ) or {}

    current_password = str(
        data.get("current_password") or ""
    )

    new_username = str(
        data.get("new_username") or ""
    )

    current_username = str(
        session.get("username") or ""
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
            "message": "用户名修改成功，请重新登录",
        }
    )


@api.post("/change-password")
@require_csrf
def change_password():
    data = request.get_json(
        silent=True
    ) or {}

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
            "message": "密码修改成功，请重新登录",
        }
    )
```
