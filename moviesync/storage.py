"""MovieSync JSON 持久化基础层。

用途：为认证、配置和订阅提供线程安全的 JSON 读写。
维护说明：写入采用临时文件 + fsync + os.replace，尽量避免程序中断造成半写入文件。
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any


class JsonStoreReadError(OSError):
    """Raised when an existing JSON store cannot be read safely."""


class JsonStore:
    def __init__(self, path: Path, default_factory: Callable[[], Any]):
        self.path = Path(path)
        self.default_factory = default_factory
        self.lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def read(self) -> Any:
        with self.lock:
            if not self.path.exists():
                return self.default_factory()
            try:
                with self.path.open("r", encoding="utf-8") as handle:
                    return json.load(handle)
            except json.JSONDecodeError:
                self._quarantine_corrupt_file()
                return self.default_factory()
            except OSError as exc:
                raise JsonStoreReadError(
                    f"无法读取 JSON 数据文件 {self.path}: {exc}"
                ) from exc

    def _quarantine_corrupt_file(self) -> None:
        """保留损坏数据副本，避免后续写入把现场直接覆盖。"""
        if not self.path.exists():
            return
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = self.path.with_name(
            f"{self.path.name}.corrupt-{stamp}"
        )
        try:
            os.replace(self.path, backup)
        except OSError:
            pass

    def write(self, value: Any) -> None:
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(value, handle, ensure_ascii=False, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temp_name, self.path)
                try:
                    self.path.chmod(0o600)
                except OSError:
                    pass

                # fsync 目录，确保 rename 本身在 Linux/EXT4 等文件系统上
                # 也尽可能落盘，降低断电后出现旧文件/新文件不一致的概率。
                try:
                    dir_fd = os.open(
                        self.path.parent,
                        os.O_RDONLY,
                    )
                    try:
                        os.fsync(dir_fd)
                    finally:
                        os.close(dir_fd)
                except OSError:
                    pass
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
