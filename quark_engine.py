import re
import requests

def sanitize_pwd_id(pwd_id):
    """自动清洗 pwd_id，无论是完整 URL 还是带斜杠的路径，都只提取纯短码 ID"""
    if not pwd_id:
        return ""
    pwd_id = str(pwd_id).strip()
    # 如果传入的是完整夸克链接，匹配其中的短码
    match = re.search(r'quark\.cn/s/([a-zA-Z0-9]+)', pwd_id)
    if match:
        return match.group(1)
    # 如果带有 URL 路径斜杠，提取最后一段
    if '/' in pwd_id:
        pwd_id = pwd_id.rstrip('/').split('/')[-1]
    # 清除问号及参数
    if '?' in pwd_id:
        pwd_id = pwd_id.split('?')[0]
    return pwd_id

def clean_tv_filename(raw_name, title=""):
    """智能从文件名中提取集数数字并清洗文件名"""
    if not raw_name:
        return None, raw_name
    
    # 匹配常见的集数格式：E01, 第01集, EP13, 13.mp4, [13]
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
                # 过滤年份如 2024, 2025, 1080p, 4k 等误判
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
            'Content-Type': 'application/json'
        }

    def check_cookie_valid(self):
        url = "https://drive.quark.cn/1/clouddrive/user/info?pr=ucpro&fr=pc"
        try:
            resp = requests.get(url, headers=self.headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return data.get('code') == 0
            return False
        except Exception:
            return False

    def get_share_files(self, pwd_id):
        # 🎯 强力清洗 pwd_id，防范 404
        pwd_id = sanitize_pwd_id(pwd_id)
        if not pwd_id:
            return None, None, "分享链接 ID 无效"

        # 1. 获取 stoken
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

        # 2. 获取文件列表
        detail_url = f"https://drive.quark.cn/1/clouddrive/share/sharepage/detail?pr=ucpro&fr=pc&pwd_id={pwd_id}&stoken={requests.utils.quote(stoken)}&p=1&num=100"
        try:
            resp = requests.get(detail_url, headers=self.headers, timeout=8)
            if resp.status_code == 404:
                return None, None, "HTTP 404 (获取文件列表失败)"
            
            data = resp.json()
            if data.get('code') != 0:
                return None, None, f"获取列表失败: {data.get('message', '未知错误')}"

            files = data.get('data', {}).get('list', [])
            return files, stoken, None
        except Exception as e:
            return None, None, f"请求文件列表异常: {str(e)}"

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
