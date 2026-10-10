def test_storage_destination_contract():
    destination = {"id": "root", "name": "默认目录", "category": "电影", "is_default": True}
    assert destination["id"]
    assert destination["name"]
    assert destination["category"]


def test_card_management_uses_manifest_driven_editor_without_card_id_routing():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    template = (root / "templates" / "admin.html").read_text(encoding="utf-8")
    quark_card = (root / "card_templates" / "quark.py").read_text(encoding="utf-8")

    assert "function openCardFromRegistry(cardId)" in template
    assert "openGenericCard(cardId);" in template
    assert 'if (cardId === "quark")' not in template
    assert 'if (cardId === "telegram")' not in template
    assert "renderGenericCardFields(currentGenericCard.fields" in template
    assert '"key": "category_fids"' in quark_card
    assert '"key": "cookie"' in quark_card
