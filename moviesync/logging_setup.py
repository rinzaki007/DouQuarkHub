"""MovieSync 日志基础设施。

用途：同时提供内存最近日志、滚动文件日志和标准输出日志，供后台页面实时查看。
维护说明：内存日志默认保留最近 300 条；磁盘日志按 2 MiB 轮转并保留 3 个备份。
"""
from __future__ import annotations

import logging
import re
from collections import deque
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock


class RedactingFormatter(logging.Formatter):
    """格式化后统一脱敏，覆盖普通日志消息和异常 traceback。"""

    _quoted_secret = re.compile(
        r"""(?i)((?:["']?)(?:cookie|set-cookie|token|access_token|refresh_token|api[_-]?key|secret|password|authorization|credential|private[_-]?key|client_secret)(?:["']?)\s*[:=]\s*)(["'])([^"'\\r\\n]*)\\2"""
    )
    _authorization = re.compile(
        r"(?i)(\\bauthorization\\s*[:=]\\s*)(?:bearer\\s+)?[^\\s,;\\]}]+"
    )
    _plain_secret = re.compile(
        r"(?i)(\\b(?:cookie|set-cookie|token|access_token|refresh_token|api[_-]?key|secret|password|authorization|credential|private[_-]?key|client_secret)\\b\\s*[:=]\\s*)[^\\s,;\\]}]+"
    )

    @classmethod
    def redact(cls, message: str) -> str:
        message = cls._quoted_secret.sub(r"\\1[REDACTED]", message)
        message = cls._authorization.sub(r"\\1[REDACTED]", message)
        return cls._plain_secret.sub(r"\\1[REDACTED]", message)

    def format(self, record: logging.LogRecord) -> str:
        return self.redact(super().format(record))


class RingBufferHandler(logging.Handler):
    def __init__(self, maxlen: int = 300):
        super().__init__()
        self.records = deque(maxlen=maxlen)
        self._lock = Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            with self._lock:
                self.records.append(message)
        except Exception:
            self.handleError(record)

    def get_records(self) -> list[str]:
        with self._lock:
            return list(self.records)


_LOGGER_NAME = "moviesync"
_ring_handler: RingBufferHandler | None = None


def configure_logging(log_dir: Path) -> logging.Logger:
    global _ring_handler
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = RedactingFormatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")

    _ring_handler = RingBufferHandler(300)
    _ring_handler.setFormatter(formatter)
    logger.addHandler(_ring_handler)

    file_handler = RotatingFileHandler(
        log_dir / "moviesync.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger


def recent_logs() -> list[str]:
    return _ring_handler.get_records() if _ring_handler else []
