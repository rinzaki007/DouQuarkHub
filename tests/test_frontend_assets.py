"""前端图标与站点 favicon 的回归检查。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"


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


def test_fontawesome_pages_have_a_backup_cdn():
    for name in (
        "index.html",
        "admin.html",
        "login.html",
        "tasks.html",
        "resource_select.html",
    ):
        content = (TEMPLATES / name).read_text(encoding="utf-8")
        assert "cdn.jsdelivr.net/npm/@fortawesome/fontawesome-free@6.7.2/css/all.min.css" in content
        assert "cdnjs.cloudflare.com/ajax/libs/font-awesome/6.7.2/css/all.min.css" in content
