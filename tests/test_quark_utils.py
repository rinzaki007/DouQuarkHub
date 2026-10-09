"""夸克工具函数单元测试。

覆盖：分享短码清洗，以及电视剧文件名中的集数识别和分辨率误判规避。
"""
from moviesync.clients.quark import clean_tv_filename, sanitize_pwd_id


def test_sanitize_pwd_id():
    assert sanitize_pwd_id("https://pan.quark.cn/s/AbC123?pwd=1") == "AbC123"
    assert sanitize_pwd_id("AbC123") == "AbC123"
    assert sanitize_pwd_id("https://example.com/s/AbC123") == ""


def test_clean_tv_filename_avoids_resolution_as_episode():
    assert clean_tv_filename("Show.S01E02.1080p.mkv")[0] == 2
    assert clean_tv_filename("Show.1080p.mkv")[0] is None
    assert clean_tv_filename("Show.第12集.mkv")[0] == 12


def test_quark_share_listing_errors_are_not_reported_as_success(monkeypatch):
    from moviesync.clients.http import ApiError
    from moviesync.clients.quark import QuarkClient

    client = QuarkClient("cookie")

    def fail(*args, **kwargs):
        raise ApiError("temporary upstream failure")

    monkeypatch.setattr(client.http, "request_json", fail)

    files, stoken, error = client.get_share_files("AbC123")
    assert files is None
    assert stoken is None
    assert "temporary upstream failure" in error


def test_quark_save_timeout_is_reported_as_uncertain(monkeypatch):
    from moviesync.clients.http import ApiError
    from moviesync.clients.quark import QuarkClient

    client = QuarkClient("cookie")

    def fail(*args, **kwargs):
        raise ApiError("Read timed out")

    monkeypatch.setattr(client.http, "request_json", fail)
    ok, message = client.save_files("AbC123", [{"fid": "file1"}], "token", "0")

    assert ok is False
    assert "转存结果不确定" in message
    assert "检查目标目录" in message
