"""MovieSync Python 包入口。

用途：提供 create_app 兼容导出，让旧启动方式仍可从 moviesync 包创建 Flask 应用。
"""
def create_app(*args, **kwargs):
    from .app import create_app as factory
    return factory(*args, **kwargs)


__all__ = ["create_app"]
