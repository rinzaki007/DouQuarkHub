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
