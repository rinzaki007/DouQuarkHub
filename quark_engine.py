import re
import requests

# 🎯 严格校验视频文件扩展名，排除 .flac / .mp3 / .pdf / .txt 等干扰文件
VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.m4v', '.rmvb', '.rm', '.ts', '.webm', '.iso', '.m2ts'}

def is_video_file(filename):
    if not filename:
        return False
    ext = filename.lower()[filename.rfind('.'):] if '.' in filename else ''
    return ext in VIDEO_EXTS

def sanitize_pwd_id(pwd_id):
    if not pwd_id:
        return ""
    pwd_id = str(pwd_id).strip()
    match = re.search(r'quark\.cn/s/([a-zA-Z0-9]+)', pwd_id)
    if match:
        return match.group(1)
    if '/' in pwd_id:
        pwd_id = pwd_id.rstrip('/').split('/')[-1]
    if '?' in pwd_id:
        pwd_id = pwd_id.split('?')[0]
    return pwd_id

def clean_tv_filename(raw_name, title=""):
    # 非视频文件直接排除
    if not raw_name or not is_video_file(raw_name):
        return None, raw_name
    
    patterns = [
        r'[E|e][P|p]?\s*(\d{1,4})',
        r'第\s*(\d{1,4})\s*[集|话|期]',
        r'\[(\d{1,4})\]',
        r'(?<!\d)(\d{1,4})(?!\d)'
    ]
    
    ep_num = None
    for pattern in patterns:
        m = re.search(pattern, raw_name)
        if m:
            try:
                ep_num = int(m.group(1))
                if ep_num > 1900 and ep_num < 2030:
                    ep_num = None
                    continue
                if ep_num in [720, 1080, 2160, 4]:
                    ep_num = None
                    continue
                break
            except ValueError:
                continue

    cleaned_name = raw_name
    return ep_num, cleaned_name


class QuarkEngine:
    def __init__(self, cookie):
        self.cookie = cookie
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Cookie': cookie,
            'Referer': 'https://pan.quark.cn/',
            'Origin': 'https://pan.quark.cn',
            'Content-Type': 'application/json'
        }

    def check_cookie_valid(self):
        url = "https://drive.quark.cn/1/clouddrive/file/sort?pr=ucpro&fr=pc&pdir_fid=0&num=1"
        try:
            resp = requests.get(url, headers=self.headers, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                return data.get('code') == 0
            return False
        except Exception:
            return False

    def get_or_create_subfolder(self, title, target_fid='0'):
        """🎯 核心：在存储目录下检查或新建以【影视名称】命名的专属子文件夹，返回其 fid"""
        if not title or not self.cookie:
            return target_fid
        
        # 清洗文件名合法字符
        safe_title = re.sub(r'[\\/:*?"<>|]', '', title).strip()
        if not safe_title:
            safe_title = title.strip()

        # 1. 检查目标目录下是否已存在同名文件夹
        sort_url = f"https://drive.quark.cn/1/clouddrive/file/sort?pr=ucpro&fr=pc&pdir_fid={target_fid}&num=100"
        try:
            r = requests.get(sort_url, headers=self.headers, timeout=6)
            if r.status_code == 200:
                data = r.json()
                if data.get('code') == 0:
                    file_list = data.get('data', {}).get('list', [])
                    for f in file_list:
                        if (f.get('dir_file') is True or f.get('file_type') == 0) and f.get('file_name') == safe_title:
                            return f.get('fid')
        except Exception:
            pass

        # 2. 不存在时自动在夸克网盘新建专属文件夹
        mkdir_url = "https://drive.quark.cn/1/clouddrive/file/mkdir?pr=ucpro&fr=pc"
        payload = {
            "file_name": safe_title,
            "pdir_fid": str(target_fid)
        }
        try:
            resp = requests.post(mkdir_url, json=payload, headers=self.headers, timeout=8)
            data = resp.json()
            if data.get('code') == 0:
                new_fid = data.get('data', {}).get('fid')
                if new_fid:
                    return new_fid
        except Exception:
            pass

        return target_fid

    def get_share_files(self, pwd_id, max_depth=3, only_video=True):
        """🎯 递归穿透文件夹，并严格过滤仅保留视频文件"""
        pwd_id = sanitize_pwd_id(pwd_id)
        if not pwd_id:
            return None, None, "分享链接 ID 无效"

        token_url = "https://drive.quark.cn/1/clouddrive/share/sharepage/token"
        payload = {"pwd_id": pwd_id, "passcode": ""}
        try:
            resp = requests.post(token_url, json=payload, headers=self.headers, timeout=8)
            if resp.status_code == 404:
                return None, None, "HTTP 404 (链接失效或删除)"
            
            data = resp.json()
            if data.get('code') != 0:
                return None, None, f"获取 Token 失败: {data.get('message', '未知错误')}"
            
            stoken = data.get('data', {}).get('stoken')
        except Exception as e:
            return None, None, f"请求 Token 异常: {str(e)}"

        all_files = []

        def fetch_folder_files(pdir_fid, current_depth):
            if current_depth > max_depth:
                return
            detail_url = f"https://drive.quark.cn/1/clouddrive/share/sharepage/detail?pr=ucpro&fr=pc&pwd_id={pwd_id}&stoken={requests.utils.quote(stoken)}&pdir_fid={pdir_fid}&p=1&num=200"
            try:
                r = requests.get(detail_url, headers=self.headers, timeout=8)
                if r.status_code == 200:
                    d = r.json()
                    if d.get('code') == 0:
                        items = d.get('data', {}).get('list', [])
                        for item in items:
                            is_dir = item.get('dir_file') is True or item.get('file_type') == 0
                            if is_dir:
                                fetch_folder_files(item.get('fid'), current_depth + 1)
                            else:
                                file_name = item.get('file_name', '')
                                # 过滤非视频文件（如 flac/mp3/pdf/txt）
                                if not only_video or is_video_file(file_name):
                                    all_files.append(item)
            except Exception:
                pass

        fetch_folder_files('0', 0)
        return all_files, stoken, None

    def save_files(self, pwd_id, files_to_save, stoken, target_fid='0'):
        pwd_id = sanitize_pwd_id(pwd_id)
        url = "https://drive.quark.cn/1/clouddrive/share/sharepage/save?pr=ucpro&fr=pc"
        fid_list = [f['fid'] for f in files_to_save if 'fid' in f]
        
        if not fid_list:
            return False, "没有包含符合要求的视频文件"

        payload = {
            "pwd_id": pwd_id,
            "stoken": stoken,
            "fid_list": fid_list,
            "to_pdir_fid": str(target_fid)
        }
        
        try:
            resp = requests.post(url, json=payload, headers=self.headers, timeout=10)
            data = resp.json()
            if data.get('code') == 0:
                return True, "转存成功"
            return False, data.get('message', '转存失败')
        except Exception as e:
            return False, str(e)
