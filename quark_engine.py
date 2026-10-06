import requests
import json
import re

def clean_tv_filename(raw_name, title):
    """解析提取集数与洗净文件名"""
    ep_match = re.search(r'E(\d{1,3})', raw_name, re.I) or re.search(r'第(\d{1,3})集', raw_name)
    ep_num = int(ep_match.group(1)) if ep_match else None
    
    ext = ''
    if '.' in raw_name:
        ext = raw_name.split('.')[-1]
    
    if ep_num is not None:
        cleaned_name = f"{title}.S01E{ep_num:02d}.{ext}" if ext else f"{title}.S01E{ep_num:02d}"
    else:
        cleaned_name = raw_name
    return ep_num, cleaned_name

class QuarkEngine:
    def __init__(self, cookie):
        self.cookie = cookie
        self.headers = {
            "Cookie": self.cookie,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Content-Type": "application/json"
        }

    def check_cookie_valid(self):
        url = "https://drive-pc.quark.cn/1/clouddrive/user/info"
        try:
            resp = requests.get(url, headers=self.headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("status") == 200 or data.get("code") == 0
        except Exception:
            pass
        return False

    def get_or_create_subfolder(self, folder_name, parent_fid='0'):
        """
        在 parent_fid 目录下检索或新建名为 folder_name 的专属文件夹，返回该文件夹的 fid
        """
        if not parent_fid:
            parent_fid = '0'

        headers = {
            "Cookie": self.cookie,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Content-Type": "application/json"
        }

        # 1. 先检查父目录下是否已存在同名文件夹
        try:
            list_url = f"https://drive-pc.quark.cn/1/clouddrive/file/sort?pdir_fid={parent_fid}&file_type=0&_size=100"
            res = requests.get(list_url, headers=headers, timeout=5).json()
            file_list = res.get("data", {}).get("list", []) or res.get("list", [])
            for item in file_list:
                if item.get("file_name") == folder_name:
                    return item.get("fid")
        except Exception as e:
            print(f"查找文件夹异常: {e}")

        # 2. 调用 Quark mkdir 接口新建文件夹
        mkdir_url = "https://drive-pc.quark.cn/1/clouddrive/file/mkdir"
        payload = {
            "pdir_fid": parent_fid,
            "file_name": folder_name,
            "dir_init_lock": False
        }

        try:
            res = requests.post(mkdir_url, json=payload, headers=headers, timeout=5).json()
            if res.get("status") == 200 or res.get("code") == 0:
                new_fid = res.get("data", {}).get("fid")
                if new_fid:
                    return new_fid
            
            # 如果文件夹已存在 (错误码 41013)
            if res.get("code") == 41013 or res.get("status") == 41013:
                list_url = f"https://drive-pc.quark.cn/1/clouddrive/file/sort?pdir_fid={parent_fid}&file_type=0&_size=100"
                res_list = requests.get(list_url, headers=headers, timeout=5).json()
                for item in res_list.get("data", {}).get("list", []):
                    if item.get("file_name") == folder_name:
                        return item.get("fid")
        except Exception as e:
            print(f"新建文件夹异常: {e}")

        return parent_fid

    def get_share_files(self, pwd_id, only_video=True):
        """解析分享链接内部文件"""
        url = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/detail"
        params = {"pwd_id": pwd_id, "_size": 100}
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == 200 or data.get("code") == 0:
                    stoken = data.get("data", {}).get("stoken", "")
                    raw_files = data.get("data", {}).get("list", [])
                    if only_video:
                        video_files = [f for f in raw_files if not f.get("dir") and any(f.get("file_name", "").lower().endswith(ext) for ext in ['.mp4', '.mkv', '.avi', '.mov', '.flv'])]
                        return video_files, stoken, None
                    return raw_files, stoken, None
                return None, None, data.get("message", "解析接口返回错误")
        except Exception as e:
            return None, None, str(e)
        return None, None, "无法解析该分享链接"

    def save_files(self, pwd_id, files, stoken, target_fid='0'):
        """转存文件至指定目录 FID"""
        url = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/save"
        payload = {
            "pwd_id": pwd_id,
            "stoken": stoken,
            "fid_list": [f['fid'] for f in files],
            "to_pdir_fid": target_fid
        }
        try:
            resp = requests.post(url, json=payload, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == 200 or data.get("code") == 0:
                    return True, "转存成功"
                return False, data.get("message", "转存失败")
        except Exception as e:
            return False, str(e)
        return False, "请求转存接口超时"
