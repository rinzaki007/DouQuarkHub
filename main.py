# MovieSync 启动入口
# 用途：创建 Flask 应用，并提供 Gunicorn 与直接 python 启动两种入口。
# 维护说明：当前版本将实际应用创建集中到 moviesync.app.create_app；此文件只负责启动，不承载业务逻辑。
import atexit

from moviesync.app import create_app

app = create_app()
atexit.register(app.extensions["moviesync"]["shutdown"])


if __name__ == "__main__":
    settings = app.extensions["moviesync_settings"]
    app.run(host=settings.host, port=settings.port, debug=settings.debug)
