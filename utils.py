import os
import re
import json

# 自动创建 data 目录并指定配置文件路径
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(DATA_DIR, exist_ok=True)
CHANNELS_FILE = os.path.join(DATA_DIR, 'channels.json')

# 默认频道列表留空，由用户在网页端自行添加或导入
DEFAULT_CHANNELS = []

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
