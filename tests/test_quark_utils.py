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
