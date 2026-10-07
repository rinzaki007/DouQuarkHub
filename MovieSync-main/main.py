from moviesync.app import create_app


app = create_app()


if __name__ == "__main__":
    settings = app.extensions["moviesync_settings"]
    app.run(host=settings.host, port=settings.port, debug=settings.debug)
