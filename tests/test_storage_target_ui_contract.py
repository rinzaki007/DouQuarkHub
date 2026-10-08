def test_storage_destination_contract():
    destination = {"id": "root", "name": "默认目录", "category": "电影", "is_default": True}
    assert destination["id"]
    assert destination["name"]
    assert destination["category"]
