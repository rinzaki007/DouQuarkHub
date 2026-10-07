"""Backward-compatible exports for older MovieSync integrations."""

from moviesync.clients.quark import QuarkClient, clean_tv_filename, sanitize_pwd_id

QuarkEngine = QuarkClient

__all__ = ["QuarkEngine", "sanitize_pwd_id", "clean_tv_filename"]
