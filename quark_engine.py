import re
import requests

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
    if not raw_name:
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
                if 1900 < ep_num < 2030 or ep_num in [720, 1080, 2160, 4]:
                    ep_num = None
                    continue
                break
            except ValueError:
                continue

    return ep_num, raw_name


class QuarkEngine:
    def __init__(self, cookie):
        if cookie:
            cookie = "".join(cookie.splitlines()).strip()
            if cookie.lower().startswith('cookie:'):
                cookie = cookie[7:].strip()
        self.cookie = cookie
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Cookie': self.cookie,
            'Referer': 'https://pan.quark.cn/',
            'Origin': 'https://pan.quark.cn',
            'Content-Type': 'application/json'
        }

    def check_cookie_valid(self):
        if not self.cookie:
            return False
        url = "https://drive.quark.cn/1/clouddrive/file/sort?pr=ucpro&fr=pc&pdir_fid=0&num=1"
        try:
            resp = requests.get(url, headers=self.headers, timeout=6)
            if resp.status_code == 200:
                return resp.json().get('code') == 0
            return False
        except Exception:
            return False

    def get_or_create_subfolder(self, folder_name, parent_fid='0'):
        """在指定的父级目录 FID 下精准创建或获取专属文件夹（含强力容错兜底）"""
        if not parent_fid:
            parent_fid = '0'

        # 1. 先检查该目录下是否存在同名字文件夹
        try:
            list_url = f"https://drive.quark.cn/1/clouddrive/file/sort?pr=ucpro&fr=pc&pdir_fid={parent_fid}&num=200"
            resp = requests.get(list_url, headers=self.headers, timeout=6)
            if resp.status_code == 200:
                d = resp.json()
                if d.get('code') == 0:
                    for item in d.get('data', {}).get('list', []):
                        if item.get('file_name') == folder_name:
                            return item.get('fid')
        except Exception:
            pass

        # 2. 发起新建文件夹请求
        mkdir_url = "https://drive.quark.cn/1/clouddrive/file/mkdir?pr=ucpro&fr=pc"
        payload = {
            "pdir_fid": str(parent_fid),
            "file_name": folder_name,
            "dir_init_lock": False
        }
        try:
            resp = requests.post(mkdir_url, json=payload, headers=self.headers, timeout=6)
            d = resp.json()
            if d.get('code') == 0:
                data_obj = d.get('data', {})
                new_fid = data_obj.get('fid') or data_obj.get('file_id') or d.get('fid')
                if new_fid:
                    return new_fid
        except Exception:
            pass

        # 3. 兜底保障：无论创建成功与否、或是因为重名报错，再次拉取目录直接定位该文件夹 FID
        try:
            list_url = f"https://drive.quark.cn/1/clouddrive/file/sort?pr=ucpro&fr=pc&pdir_fid={parent_fid}&num=200"
            resp = requests.get(list_url, headers=self.headers, timeout=6)
            if resp.status_code == 200:
                d = resp.json()
                if d.get('code') == 0:
                    for item in d.get('data', {}).get('list', []):
                        if item.get('file_name') == folder_name:
                            return item.get('fid')
        except Exception:
            pass

        return None

    def get_share_files(self, pwd_id, max_depth=3):
        pwd_id = sanitize_pwd_id(pwd_id)
        if not pwd_id:
            return None, None, "分享链接 ID 无效"

        token_url = "https://drive.quark.cn/1/clouddrive/share/sharepage/token"
        payload = {"pwd_id": pwd_id, "passcode": ""}
        try:
            resp = requests.post(token_url, json=payload, headers=self.headers, timeout=8)
            if resp.status_code == 404:
                return None, None, "HTTP 404 (该链接已失效或已被原作者删除)"
            
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
                            if item.get('dir_file') is True or item.get('file_type') == 0:
                                fetch_folder_files(item.get('fid'), current_depth + 1)
                            else:
                                all_files.append(item)
            except Exception:
                pass

        fetch_folder_files('0', 0)
        return all_files, stoken, None

    def save_files(self, pwd_id, files_to_save, stoken, target_fid='0'):
        pwd_id = sanitize_pwd_id(pwd_id)
        url = "https://drive.quark.cn/1/clouddrive/share/sharepage/save?pr=ucpro&fr=pc"
        fid_list = [f['fid'] for f in files_to_save if 'fid' in f]
        
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
