import requests
import json
import re

def clean_tv_filename(raw_name, title):
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
        # 🎯 补全夸克 PC/Web 端防风控通用请求头
        self.headers = {
            "Cookie": self.cookie,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://pan.quark.cn/",
            "Origin": "https://pan.quark.cn",
            "Content-Type": "application/json"
        }

    def check_cookie_valid(self):
        """精准校验夸克 Cookie 是否有效"""
        url = "https://drive-pc.quark.cn/1/clouddrive/user/info?pr=uc_drive&fr=pc"
        try:
            resp = requests.get(url, headers=self.headers, timeout=6)
            if resp.status_code == 200:
                data = resp.json()
                # 兼容 status 200 或 code 0
                return data.get("status") == 200 or data.get("code") == 0 or data.get("message") == "ok"
        except Exception:
            pass
        return False

    def get_or_create_subfolder(self, folder_name, parent_fid='0'):
        if not parent_fid:
            parent_fid = '0'

        try:
            list_url = f"https://drive-pc.quark.cn/1/clouddrive/file/sort?pdir_fid={parent_fid}&file_type=0&_size=100&pr=uc_drive&fr=pc"
            res = requests.get(list_url, headers=self.headers, timeout=5).json()
            file_list = res.get("data", {}).get("list", []) or res.get("list", [])
            for item in file_list:
                if item.get("file_name") == folder_name:
                    return item.get("fid")
        except Exception as e:
            print(f"查找文件夹异常: {e}")

        mkdir_url = "https://drive-pc.quark.cn/1/clouddrive/file/mkdir?pr=uc_drive&fr=pc"
        payload = {
            "pdir_fid": parent_fid,
            "file_name": folder_name,
            "dir_init_lock": False
        }

        try:
            res = requests.post(mkdir_url, json=payload, headers=self.headers, timeout=5).json()
            if res.get("status") == 200 or res.get("code") == 0:
                new_fid = res.get("data", {}).get("fid")
                if new_fid:
                    return new_fid
            
            if res.get("code") == 41013 or res.get("status") == 41013:
                list_url = f"https://drive-pc.quark.cn/1/clouddrive/file/sort?pdir_fid={parent_fid}&file_type=0&_size=100&pr=uc_drive&fr=pc"
                res_list = requests.get(list_url, headers=self.headers, timeout=5).json()
                for item in res_list.get("data", {}).get("list", []):
                    if item.get("file_name") == folder_name:
                        return item.get("fid")
        except Exception as e:
            print(f"新建文件夹异常: {e}")

        return parent_fid

    def get_share_files(self, pwd_id, pdir_fid="0", only_video=True):
        url = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/detail"
        params = {
            "pwd_id": pwd_id,
            "pdir_fid": pdir_fid,
            "_size": 100,
            "pr": "uc_drive",
            "fr": "pc"
        }
        
        detail_headers = self.headers.copy()
        detail_headers["Referer"] = f"https://pan.quark.cn/s/{pwd_id}"

        try:
            resp = requests.get(url, headers=detail_headers, params=params, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == 200 or data.get("code") == 0:
                    stoken = data.get("data", {}).get("stoken", "")
                    raw_files = data.get("data", {}).get("list", []) or []
                    
                    video_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.m4v')
                    result_files = []

                    for f in raw_files:
                        if f.get("dir"):
                            sub_files, _, _ = self.get_share_files(pwd_id, pdir_fid=f.get("fid"), only_video=only_video)
                            if sub_files:
                                result_files.extend(sub_files)
                        else:
                            if only_video:
                                if any(f.get("file_name", "").lower().endswith(ext) for ext in video_extensions):
                                    result_files.append(f)
                            else:
                                result_files.append(f)

                    return result_files, stoken, None
                
                msg = data.get("message") or data.get("msg") or "夸克未返回有效内容"
                return None, None, msg
            return None, None, f"HTTP {resp.status_code}"
        except Exception as e:
            return None, None, str(e)

    def save_files(self, pwd_id, files, stoken, target_fid='0'):
        """🎯 修复 460 错误：转存接口绑定正确的 pr/fr 参数与防风控 Header"""
        url = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/save?pr=uc_drive&fr=pc"
        payload = {
            "pwd_id": pwd_id,
            "stoken": stoken,
            "fid_list": [f['fid'] for f in files],
            "to_pdir_fid": target_fid
        }
        
        save_headers = self.headers.copy()
        save_headers["Referer"] = f"https://pan.quark.cn/s/{pwd_id}"

        try:
            resp = requests.post(url, json=payload, headers=save_headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == 200 or data.get("code") == 0:
                    return True, "转存成功"
                return False, data.get("message", "转存失败")
            elif resp.status_code == 460:
                return False, "触发夸克风控 (HTTP 460)，请更换 Cookie 或稍后再试"
            return False, f"HTTP 状态码: {resp.status_code}"
        except Exception as e:
            return False, str(e)
        return False, "请求转存接口超时"
