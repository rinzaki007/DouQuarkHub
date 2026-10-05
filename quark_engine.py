import requests
import json

class QuarkEngine:
    def __init__(self, cookie):
        self.cookie = cookie.strip() if cookie else ""
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://pan.quark.cn/",
            "Origin": "https://pan.quark.cn",
            "Cookie": self.cookie,
            "Accept": "application/json, text/plain, */*"
        }

    def check_cookie_valid(self):
        """校验 Cookie 是否有效"""
        if not self.cookie:
            return False
        url = "https://drive-pc.quark.cn/1/clouddrive/user/info?pr=ucpro&fr=pc"
        try:
            resp = requests.get(url, headers=self.headers, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("code") == 0 or "data" in data
            return False
        except Exception:
            return False

    def get_share_files(self, pwd_id):
        """获取分享链接的文件列表与 stoken"""
        url = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/detail"
        params = {"pr": "ucpro", "fr": "pc", "pwd_id": pwd_id}
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=10)
            if resp.status_code == 200:
                res_json = resp.json()
                if res_json.get("code") == 0 and "data" in res_json:
                    data = res_json["data"]
                    files = data.get("list", [])
                    stoken = data.get("stoken", "")
                    share_id = data.get("share_id", "")
                    return files, stoken, share_id
            return [], "", ""
        except Exception:
            return [], "", ""

    def save_files(self, fids, target_fid, share_id, stoken):
        """转存文件到指定目录"""
        url = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/save?pr=ucpro&fr=pc"
        payload = {
            "fid_list": fids,
            "to_pdir_fid": target_fid,
            "share_id": share_id,
            "stoken": stoken,
            "scene": "share"
        }
        try:
            resp = requests.post(url, headers=self.headers, json=payload, timeout=12)
            if resp.status_code == 200:
                res_json = resp.json()
                if res_json.get("code") == 0:
                    return True, "转存成功"
                return False, res_json.get("message", "接口返回转存错误")
            return False, f"HTTP 状态码异常: {resp.status_code}"
        except Exception as e:
            return False, f"网络异常: {str(e)}"
