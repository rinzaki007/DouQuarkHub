from moviesync.services.filename_rules import (
    DEFAULT_TV_MAGIC_REGEX,
    extract_filename_tokens,
    parse_tv_episode,
    render_filename_template,
)


def test_tv_magic_regex_parses_common_release_names():
    assert parse_tv_episode("Stranger.Things.S04E01.2022.NF.WEB-DL.2160p.HEVC.HDR.DDP.mkv") == (4, 1)
    assert parse_tv_episode("Stranger.Things.S02E09.2160p.BluRay.x265.10bit.DTS.mkv") == (2, 9)
    assert parse_tv_episode("Show.S01E08.mkv", DEFAULT_TV_MAGIC_REGEX) == (1, 8)


def test_episode_parser_keeps_legacy_episode_only_names():
    assert parse_tv_episode("兰香如故 第47集.mkv") == (None, 47)
    assert parse_tv_episode("Show.EP12.mp4") == (None, 12)


def test_invalid_custom_magic_regex_falls_back_to_standard_parser():
    assert parse_tv_episode("Show.S02E03.mkv", {"pattern": "(", "replace": ""}) == (2, 3)


def test_filename_template_tokens():
    file_name = "黑镜.S02E03.2023-10-26.高清版.mkv"
    tokens = extract_filename_tokens(file_name, "黑镜")
    assert tokens["TASKNAME"] == "黑镜"
    assert tokens["S"] == "02"
    assert tokens["SXX"] == "S02"
    assert tokens["E"] == "3"
    assert tokens["EXT"] == "mkv"
    assert tokens["DATE"] == "20231026"
    assert tokens["YEAR"] == "2023"
    assert tokens["CHINESE"] == "黑镜"
    assert tokens["VER"] == "高清版"
    assert render_filename_template(file_name, "{TASKNAME}.{SXX}E{II}.{EXT}", "黑镜") == "黑镜.S02E03.mkv"
    assert render_filename_template(file_name, "{TASKNAME}.{SXX}E{III}.{EXT}", "黑镜") == "黑镜.S02E003.mkv"


def test_episode_parser_supports_pure_numeric_filenames():
    assert parse_tv_episode("1.mkv") == (None, 1)
    assert parse_tv_episode("2.mp4") == (None, 2)
    assert parse_tv_episode("003.avi") == (None, 3)
    assert parse_tv_episode("1080.mkv") == (None, None)
    assert parse_tv_episode("2024.mp4") == (None, None)
    assert parse_tv_episode("Show.1080p.mkv") == (None, None)
