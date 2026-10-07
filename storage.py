from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable


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
            except (OSError, json.JSONDecodeError):
                return self.default_factory()

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
            finally:
                if os.path.exists(temp_name):
                    os.unlink(temp_name)
