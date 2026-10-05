import os
import re
import json

CHANNELS_FILE = os.path.join(os.path.dirname(__file__), 'channels.json')

DEFAULT_CHANNELS = [
    {"name": "夸克云盘综合资源", "id": "Quark_Movies"},
    {"name": "YOYO资源|夸克|短剧", "id": "yoyokuakeduanju"},
    {"name": "UC夸克百度迅雷资源分享", "id": "ucquark"},
    {"name": "夸克网盘资源收藏夹", "id": "QuarkFree"},
    {"name": "leo资源(夸克)", "id": "leoziyuan"},
    {"name": "夸克（百草）", "id": "baicaoZY"},
    {"name": "夸克(网盘高分影视)", "id": "SharePanFilms"},
    {"name": "夸克(书籍)", "id": "BooksRealm"},
    {"name": "Q_dongman", "id": "Q_dongman"},
    {"name": "夸克网盘动漫资源", "id": "kuakedongman"},
    {"name": "kduanju", "id": "kduanju"},
    {"name": "Q_jilupian", "id": "Q_jilupian"},
    {"name": "yunpanquark", "id": "yunpanquark"},
    {"name": "Q_dianying", "id": "Q_dianying"},
    {"name": "gokuapan", "id": "gokuapan"},
    {"name": "kuyupan", "id": "kuyupan"},
    {"name": "kuakenetpan", "id": "kuakenetpan"}
]

QUARK_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://pan.quark.cn/",
    "Origin": "https://pan.quark.cn",
    "Accept": "application/json, text/plain, */*"
}

DOUBAN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://movie.douban.com/"
}

VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.rmvb', '.flv', '.wmv', '.ts', '.m3u8', '.iso', '.m4v'}

def is_video_file(filename):
    if not filename:
        return False
    ext = os.path.splitext(filename.lower())[1]
    return ext in VIDEO_EXTENSIONS

def is_garbled_name(text):
    if not text:
        return True
    bad_chars = re.findall(r'[^\u4e00-\u9fa5\u3040-\u30ff\u31f0-\u31ffa-zA-Z0-9\s\.\_\-\(\)\[\]\（\）\【\】\:\：\!\！]', text)
    if len(bad_chars) > 3 or (len(text) > 0 and len(bad_chars) / len(text) > 0.25):
        return True
    return False

def load_channels():
    if not os.path.exists(CHANNELS_FILE):
        save_channels(DEFAULT_CHANNELS)
        return DEFAULT_CHANNELS
    try:
        with open(CHANNELS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, list) else DEFAULT_CHANNELS
    except Exception:
        return DEFAULT_CHANNELS

def save_channels(channels):
    try:
        with open(CHANNELS_FILE, 'w', encoding='utf-8') as f:
            json.dump(channels, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False