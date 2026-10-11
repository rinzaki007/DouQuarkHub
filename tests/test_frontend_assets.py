"""前端图标与站点 favicon 的回归检查。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
LOCAL_FONT_AWESOME = ROOT / "static" / "vendor" / "fontawesome"


def test_all_pages_declare_a_local_favicon():
    for name in (
        "index.html",
        "admin.html",
        "login.html",
        "tasks.html",
        "resource_select.html",
        "about.html",
    ):
        content = (TEMPLATES / name).read_text(encoding="utf-8")
        assert 'rel="icon"' in content, f"{name} 缺少站点图标声明"
        assert "favicon.svg" in content, f"{name} 未使用本地 favicon"


def test_fontawesome_is_served_only_from_local_assets():
    for name in (
        "index.html",
        "admin.html",
        "login.html",
        "tasks.html",
        "resource_select.html",
        "playback.html",
    ):
        content = (TEMPLATES / name).read_text(encoding="utf-8")
        assert "vendor/fontawesome/css/all.min.css" in content
        assert "fontawesome-free@6.7.2" not in content
        assert "cdnjs.cloudflare.com/ajax/libs/font-awesome" not in content

    css = LOCAL_FONT_AWESOME / "css" / "all.min.css"
    assert css.is_file(), "缺少本地 Font Awesome 样式文件"
    stylesheet = css.read_text(encoding="utf-8")
    assert "../webfonts/fa-solid-900.woff2" in stylesheet
    assert (LOCAL_FONT_AWESOME / "webfonts" / "fa-solid-900.woff2").is_file()
    assert (LOCAL_FONT_AWESOME / "webfonts" / "fa-regular-400.woff2").is_file()
    assert (LOCAL_FONT_AWESOME / "webfonts" / "fa-brands-400.woff2").is_file()
