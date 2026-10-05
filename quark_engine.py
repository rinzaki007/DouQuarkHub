import re
import requests
import urllib.parse
from utils import QUARK_HEADERS, is_video_file, is_garbled_name

class QuarkEngine:
    def __init__(self, cookie_str):
        self.session = requests.Session()
        clean_cookie = cookie_str.strip().strip('"').strip("'")
        
        ctoken_match = re.search(r'ctoken=([^;]+)', clean_cookie)
        self.ctoken = ctoken_match.group(1) if ctoken_match else ""
        
        headers = QUARK_HEADERS.copy()
        headers["Cookie"] = clean_cookie
        if self.ctoken:
            headers["x-ctoken"] = self.ctoken
            
        self.session.headers.update(headers)

    def _build_url(self, base_url):
        if self.ctoken:
            delimiter = "&" if "?" in base_url else "?"
            return f"{base_url}{delimiter}ctoken={self.ctoken}"
        return base_url

    def check_auth(self):
        try:
            raw_url = "https://drive-pc.quark.cn/1/clouddrive/file/sort?pr=ucpro&fr=pc&pdir_fid=0"
            url = self._build_url(raw_url)
            res = self.session.get(url, timeout=6)
            if res.status_code == 200:
                data = res.json()
                code = data.get("code")
                if code == 0:
                    return True, "账号鉴权通过"
                else:
                    msg = data.get("message") or data.get("msg") or f"错误码 code={code}"
                    return False, f"夸克拒绝对接 ({msg})"
            return False, f"HTTP 响应状态码 {res.status_code}"
        except Exception as e:
            return False, f"请求失败: {str(e)}"

    def mkdir(self, folder_name, pdir_fid="0"):
        try:
            raw_url = "https://drive-pc.quark.cn/1/clouddrive/file/mkdir?pr=ucpro&fr=pc"
            url = self._build_url(raw_url)
            payload = {
                "file_name": folder_name,
                "pdir_fid": str(pdir_fid)
            }
            res = self.session.post(url, json=payload, timeout=6)
            data = res.json()
            if res.status_code == 200 and data.get("code") == 0:
                fid = data.get("data", {}).get("fid")
                return fid, ""
            else:
                msg = data.get("message") or data.get("msg") or f"code={data.get('code')}"
                return "", msg
        except Exception as e:
            return "", str(e)

    def get_share_token(self, pwd_id):
        try:
            raw_url = "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/token?pr=ucpro&fr=pc"
            url = self._build_url(raw_url)
            payload = {"pwd_id": pwd_id, "passcode": ""}
            res = self.session.post(url, json=payload, timeout=6)
            data = res.json()
            if res.status_code == 200 and data.get("code") == 0:
                data_obj = data.get("data", {})
                stoken = data_obj.get("stoken") or data_obj.get("receive_code") or data_obj.get("receiveCode") or ""
                return stoken, ""
            else:
                msg = data.get("message") or data.get("msg") or f"code={data.get('code')}"
                return "", f"夸克返回: {msg}"
        except Exception as e:
            return "", f"网络异常: {str(e)}"

    def get_share_detail_and_validate(self, pwd_id, stoken):
        try:
            safe_stoken = urllib.parse.quote(stoken)
            safe_pwd_id = urllib.parse.quote(pwd_id)

            raw_url = f"https://drive-pc.quark.cn/1/clouddrive/share/sharepage/detail?pr=ucpro&fr=pc&pwd_id={safe_pwd_id}&stoken={safe_stoken}&pdir_fid=0&page=1&size=50"
            url = self._build_url(raw_url)
            res = self.session.get(url, timeout=6)
            data = res.json()

            if res.status_code != 200 or data.get("code") != 0:
                msg = data.get("message") or data.get("msg") or f"code={data.get('code')}"
                return [], [], False, f"夸克返回: {msg}"

            file_list = data.get("data", {}).get("list", [])
            if not file_list:
                return [], [], False, "分享链接为空（无文件）"

            for item in file_list:
                fname = item.get("file_name") or item.get("title") or ""
                if is_garbled_name(fname):
                    return [], [], False, f"资源标题异常/乱码 ({fname})"

            has_video = False
            for item in file_list:
                fname = item.get("file_name") or item.get("title") or ""
                is_dir = item.get("dir") or item.get("file_type") == 0 or item.get("is_dir")
                
                if not is_dir:
                    if is_video_file(fname):
                        has_video = True
                        break
                else:
                    sub_fid = item.get("fid") or item.get("file_id")
                    if sub_fid:
                        try:
                            sub_url = f"https://drive-pc.quark.cn/1/clouddrive/share/sharepage/detail?pr=ucpro&fr=pc&pwd_id={safe_pwd_id}&stoken={safe_stoken}&pdir_fid={sub_fid}&page=1&size=20"
                            sub_res = self.session.get(self._build_url(sub_url), timeout=5)
                            if sub_res.status_code == 200 and sub_res.json().get("code") == 0:
                                sub_list = sub_res.json().get("data", {}).get("list", [])
                                for sub_item in sub_list:
                                    sub_fname = sub_item.get("file_name") or sub_item.get("title") or ""
                                    if is_video_file(sub_fname):
                                        has_video = True
                                        break
                        except Exception:
                            pass
                if has_video:
                    break

            if not has_video:
                return [], [], False, "未检测到视频文件(仅包含音频/图片/文档等非影视资源)"

            fids, fid_tokens = [], []
            for item in file_list:
                fid = item.get("fid") or item.get("file_id") or item.get("id")
                token = item.get("share_fid_token") or item.get("fid_token") or item.get("token") or ""
                if fid:
                    fids.append(str(fid))
                    fid_tokens.append(str(token))

            is_single_folder = False
            if len(file_list) == 1:
                first = file_list[0]
                if first.get("dir") or first.get("file_type") == 0 or first.get("is_dir"):
                    is_single_folder = True

            return fids, fid_tokens, is_single_folder, ""

        except Exception as e:
            return [], [], False, f"解析异常: {str(e)}"

    def save_share_files(self, pwd_id, stoken, fids, fid_tokens, target_folder_id='0'):
        target_fid = str(target_folder_id).strip() if target_folder_id else "0"
        if not target_fid:
            target_fid = "0"

        payload = {
            "fid_list": fids,
            "fid_token_list": fid_tokens,
            "to_pdir_fid": target_fid,
            "pwd_id": pwd_id,
            "stoken": stoken,
            "receive_code": stoken,
            "pdir_fid": "0",
            "scene": "link"
        }

        candidate_urls = [
            "https://drive-pc.quark.cn/1/clouddrive/share/save?pr=ucpro&fr=pc",
            "https://drive-pc.quark.cn/1/clouddrive/share/sharepage/save?pr=ucpro&fr=pc",
            "https://drive.quark.cn/1/clouddrive/share/sharepage/save?pr=ucpro&fr=pc"
        ]

        last_error = ""
        for raw_url in candidate_urls:
            try:
                url = self._build_url(raw_url)
                res = self.session.post(url, json=payload, timeout=10)
                if res.status_code == 404:
                    last_error = f"HTTP 404 ({raw_url})"
                    continue

                try:
                    data = res.json()
                except Exception:
                    data = {}

                if res.status_code == 200 and data.get("code") == 0:
                    return True, "转存成功"
                else:
                    msg = data.get("message") or data.get("msg") or data.get("error") or "转存校验未通过"
                    code = data.get("code") if data.get("code") is not None else res.status_code
                    return False, f"夸克返回异常 (HTTP {res.status_code} | code={code} | msg={msg})"
            except Exception as e:
                last_error = str(e)
                continue

        return False, f"最终转存失败: {last_error}"
