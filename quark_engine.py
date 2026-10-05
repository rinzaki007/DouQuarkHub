import requests

class QuarkEngine:
    def __init__(self, cookie):
        self.cookie = cookie.strip() if cookie else ""
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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
                data = resp.json()
                return data.get("code") == 0
            return False
        except Exception:
            return False

    def get_stoken(self, pwd_id, passcode=""):
        url = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/token?pr=ucpro&fr=pc"
        payload = {
            "pwd_id": pwd_id,
            "passcode": passcode
        }
        headers = self.headers.copy()
        headers["Referer"] = f"https://pan.quark.cn/s/{pwd_id}"
        
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=6)
            if resp.status_code == 200:
                res_json = resp.json()
                if res_json.get("code") == 0 and "data" in res_json:
                    return res_json["data"].get("stoken", ""), ""
                return "", f"token 接口拒答: {res_json.get('message', '未知错误')}"
            return "", f"token 接口 HTTP {resp.status_code}"
        except Exception as e:
            return "", f"token 请求异常: {str(e)}"

    def get_share_files(self, pwd_id, passcode=""):
        stoken, err = self.get_stoken(pwd_id, passcode)
        if not stoken:
            return [], "", err or "未能获取到 stoken"

        url = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/detail"
        params = {
            "pr": "ucpro",
            "fr": "pc",
            "pwd_id": pwd_id,
            "stoken": stoken,
            "pdir_fid": "0",
            "_page": "1",
            "_size": "50"
        }
        headers = self.headers.copy()
        headers["Referer"] = f"https://pan.quark.cn/s/{pwd_id}"

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=8)
            if resp.status_code == 200:
                res_json = resp.json()
                code = res_json.get("code")
                if code == 0 and "data" in res_json:
                    data = res_json["data"]
                    files = data.get("list", []) or data.get("file_list", [])
                    if files:
                        return files, stoken, ""
                    return [], stoken, "分享目录为空"
                msg = res_json.get("message") or f"错误码 {code}"
                return [], "", f"detail 拒绝: {msg}"
            return [], "", f"detail 接口 HTTP {resp.status_code}"
        except Exception as e:
            return [], "", f"detail 请求异常: {str(e)}"

    def save_files(self, pwd_id, files, stoken, target_fid='0'):
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
                res_json = resp.json()
                if res_json.get("code") == 0:
                    return True, "转存成功"
                return False, res_json.get("message", "夸克拒绝转存")
            return False, f"转存 HTTP {resp.status_code}"
        except Exception as e:
            return False, f"转存请求网络异常: {str(e)}"
