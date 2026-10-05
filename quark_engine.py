import re
import requests

def clean_tv_filename(raw_filename, show_title):
    """
    自动洗剧正则匹配：过滤黑名单杂质，提取集数并组装为 Emby/Plex 标准格式
    例: "01~4K.mp4" -> (1, "兰香如故.E01.mp4")
    """
    # 1. 过滤黑名单
    black_words = ["纯享", "加更", "超前企划", "训练室", "预告", "花絮", "特辑", "广告"]
    if any(bw in raw_filename for bw in black_words):
        return None, None

    # 2. 匹配常见视频后缀
    ext_match = re.search(r'\.(mp4|mkv|mov|avi|flv)$', raw_filename, re.I)
    if not ext_match:
        return None, None
    ext = ext_match.group(1).lower()

    # 3. 集数正则表达式模式链
    patterns = [
        r'[S|s]\d+[E|e](\d{1,3})',          # S01E02
        r'[E|e](\d{1,3})',                   # E01
        r'第\s*(\d{1,3})\s*[集|话]',         # 第01集 / 第1话
        r'(?:^|[^\d])(\d{1,2})(?:~|-|\.|\b|[K|k|p|P])' # 01~4K / 01.mp4
    ]

    ep_num = None
    for pattern in patterns:
        match = re.search(pattern, raw_filename)
        if match:
            ep_num = int(match.group(1))
            break

    if ep_num is not None:
        cleaned_name = f"{show_title}.E{ep_num:02d}.{ext}"
        return ep_num, cleaned_name

    return None, raw_filename


class QuarkEngine:
    def __init__(self, cookie):
        self.cookie = cookie.strip() if cookie else ""
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://pan.quark.cn/",
            "Origin": "https://pan.quark.cn",
            "Cookie": self.cookie,
            "Content-Type": "application/json;charset=UTF-8",
            "Accept": "application/json, text/plain, */*"
        }

    def check_cookie_valid(self):
        if not self.cookie:
            return False
        url = "https://drive-pc.quark.cn/1/clouddrive/file/sort?pr=ucpro&fr=pc&pdir_fid=0&_size=1"
        try:
            resp = requests.get(url, headers=self.headers, timeout=5)
            if resp.status_code == 200:
                return resp.json().get("code") == 0
            return False
        except Exception:
            return False

    def get_stoken(self, pwd_id, passcode=""):
        url = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/token?pr=ucpro&fr=pc"
        payload = {"pwd_id": pwd_id, "passcode": passcode}
        headers = self.headers.copy()
        headers["Referer"] = f"https://pan.quark.cn/s/{pwd_id}"
        
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=6)
            if resp.status_code == 200:
                res = resp.json()
                if res.get("code") == 0 and "data" in res:
                    return res["data"].get("stoken", ""), ""
                return "", res.get('message', '未知错误')
            return "", f"HTTP {resp.status_code}"
        except Exception as e:
            return "", str(e)

    def get_share_files(self, pwd_id, pdir_fid="0", passcode=""):
        """获取分享链接的文件列表"""
        stoken, err = self.get_stoken(pwd_id, passcode)
        if not stoken:
            return [], "", err

        url = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/detail"
        params = {
            "pr": "ucpro", "fr": "pc",
            "pwd_id": pwd_id, "stoken": stoken,
            "pdir_fid": str(pdir_fid),
            "_page": "1", "_size": "100"
        }
        headers = self.headers.copy()
        headers["Referer"] = f"https://pan.quark.cn/s/{pwd_id}"

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=8)
            if resp.status_code == 200:
                res = resp.json()
                if res.get("code") == 0 and "data" in res:
                    files = res["data"].get("list", []) or res["data"].get("file_list", [])
                    return files, stoken, ""
            return [], "", f"HTTP {resp.status_code}"
        except Exception as e:
            return [], "", str(e)

    def save_files(self, pwd_id, files, stoken, target_fid='0'):
        """转存指定的包含 fid 列表的文件集合"""
        url = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/save?pr=ucpro&fr=pc"
        
        fid_list = [f.get("fid") for f in files if f.get("fid")]
        fid_token_list = [f.get("share_fid_token") or f.get("fid_token") or "" for f in files]

        if not fid_list:
            return False, "未找到有效的文件 FID"

        payload = {
            "fid_list": fid_list,
            "fid_token_list": fid_token_list,
            "to_pdir_fid": str(target_fid),
            "pwd_id": pwd_id,
            "stoken": stoken,
            "scene": "share"
        }
        headers = self.headers.copy()
        headers["Referer"] = f"https://pan.quark.cn/s/{pwd_id}"

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            if resp.status_code == 200:
                res = resp.json()
                if res.get("code") == 0:
                    return True, "转存成功"
                return False, res.get("message", "夸克拒绝转存")
            return False, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)
