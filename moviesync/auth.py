from __future__ import annotations

from pathlib import Path
from threading import Lock

from werkzeug.security import check_password_hash, generate_password_hash

from .storage import JsonStore


class AuthStore:
    def __init__(self, auth_file: Path, legacy_file: Path | None = None):
        self.store = JsonStore(auth_file, lambda: {"initialized": False})
        self.legacy_file = legacy_file
        self.lock = Lock()
        self._migrate_legacy()

    def _migrate_legacy(self) -> None:
        if self.store.path.exists() or not self.legacy_file or not self.legacy_file.exists():
            return
        try:
            import json

            data = json.loads(self.legacy_file.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("initialized") and data.get("password_hash"):
                self.store.write(data)
        except (OSError, ValueError):
            pass

    def is_initialized(self) -> bool:
        data = self.store.read()
        return bool(isinstance(data, dict) and data.get("initialized"))

    def setup(self, username: str, password: str) -> None:
        username = username.strip()
        password = password.strip()
        if len(username) < 2 or len(username) > 64:
            raise ValueError("管理员账号长度必须在 2-64 个字符之间")
        if len(password) < 8:
            raise ValueError("管理员密码至少需要 8 个字符")
        with self.lock:
            if self.is_initialized():
                raise ValueError("系统已完成初始化")
            self.store.write({
                "initialized": True,
                "username": username,
                "password_hash": generate_password_hash(password),
            })

    def verify(self, username: str, password: str) -> bool:
        data = self.store.read()
        if not isinstance(data, dict) or not data.get("initialized"):
            return False
        stored_username = data.get("username", "")
        password_hash = data.get("password_hash", "")
        return username == stored_username and bool(password_hash) and check_password_hash(password_hash, password)
