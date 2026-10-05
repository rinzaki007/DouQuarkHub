import requests

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
        if not self.cookie:
            return False
        url = "https://drive-pc.quark.cn/1/clouddrive/file/sort?pr=ucpro&fr=pc&pdir_fid=0&_size=1"
        try:
            resp = requests.get(url, headers=self.headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("code") == 0
            return False
        except Exception:
            return False

    def get_share_files(self, pwd_id):
        url = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/detail"
        params = {"pr": "ucpro", "fr": "pc", "pwd_id": pwd_id}
        try:
            resp = requests.get(url, headers=self.headers, params=params, timeout=8)
            if resp.status_code == 200:
                res_json = resp.json()
                if res_json.get("code") == 0 and "data" in res_json:
                    data = res_json["data"]
                    files = data.get("list", [])
                    stoken = data.get("stoken", "")
                    return files, stoken
            return [], ""
        except Exception:
            return [], ""

    def save_files(self, pwd_id, files, stoken, target_fid='0'):
        url = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/save?pr=ucpro&fr=pc"
        
        fid_list = [f.get("fid") for f in files if f.get("fid")]
        fid_token_list = [f.get("share_fid_token") or f.get("fid_token") or "" for f in files]

        if not fid_list:
            return False, "未获取到有效的文件 ID"

        payload = {
            "fid_list": fid_list,
            "fid_token_list": fid_token_list,
            "to_pdir_fid": str(target_fid),
            "pwd_id": pwd_id,
            "stoken": stoken,
            "scene": "share"
        }

        try:
            resp = requests.post(url, headers=self.headers, json=payload, timeout=10)
            if resp.status_code == 200:
                res_json = resp.json()
                if res_json.get("code") == 0:
                    return True, "转存成功"
                return False, res_json.get("message", "夸克接口拒绝转存")
            return False, f"HTTP 状态码: {resp.status_code}"
        except Exception as e:
            return False, f"网络请求异常: {str(e)}"
