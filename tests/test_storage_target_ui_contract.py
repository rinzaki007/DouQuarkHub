def test_storage_destination_contract():
    destination = {"id": "root", "name": "默认目录", "category": "电影", "is_default": True}
    assert destination["id"]
    assert destination["name"]
    assert destination["category"]


def test_quark_card_uses_dedicated_editor_with_dynamic_directory_fields():
    from pathlib import Path

    template = (Path(__file__).resolve().parents[1] / "templates" / "admin.html").read_text(encoding="utf-8")

    assert 'if (cardId === "quark")' in template
    assert 'openQuarkCard();' in template
    assert 'id="quark-card-category-fids"' in template
    assert "renderQuarkCategoryFids(cfg.category_fids || {})" in template
    assert 'document.querySelectorAll("#quark-card-category-fids [data-quark-category]")' in template
    assert 'type="password" autocomplete="new-password"' in template
    assert "quark-card-fid-movie" not in template
    assert "quark-card-fid-tv" not in template
