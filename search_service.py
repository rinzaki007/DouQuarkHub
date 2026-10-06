import requests
import re
from quark_engine import QuarkEngine, sanitize_pwd_id, is_video_file

class SearchService:
    def __init__(self, cookie):
        self.cookie = cookie
        self.engine = QuarkEngine(cookie)

    def search_single_movie_pwd_id(self, title, channels):
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        
        for ch in channels:
            ch_id = ch.get('id', '').strip()
            if not ch_id:
                continue
            
            url = f"https://t.me/s/{ch_id}?q={requests.utils.quote(title)}"
            try:
                resp = requests.get(url, headers=headers, timeout=5)
                if resp.status_code == 200:
                    matches = re.findall(r'pan\.quark\.cn/s/([a-zA-Z0-9]+)', resp.text)
                    for pwd_id in matches:
                        files, stoken, err = self.engine.get_share_files(pwd_id, only_video=True)
                        if files and len(files) > 0:
                            return pwd_id
            except Exception:
                continue
        return None

    def batch_search_and_transfer_stream(self, movie_titles, channels, target_fid='0'):
        for title in movie_titles:
            yield f"\n🔍 正在检索: [{title}]..."
            
            pwd_id = self.search_single_movie_pwd_id(title, channels)
            if not pwd_id:
                yield f"❌ 未能找到包含有效视频文件的夸克链接: [{title}]"
                continue

            yield f"🟢 找到视频资源链接 ID: {pwd_id}，正在穿透解析内容..."
            files, stoken, err = self.engine.get_share_files(pwd_id, only_video=True)
            
            if not files:
                yield f"⚠️ 链接解析失败或未发现有效视频文件: {err}"
                continue

            # 自动定位或创建专属文件夹
            show_folder_fid = self.engine.get_or_create_subfolder(title, target_fid)
            yield f"📁 已建立/定位专属目录: [{title}] (FID: {show_folder_fid})"

            ok, msg = self.engine.save_files(pwd_id, files, stoken, show_folder_fid)
            if ok:
                yield f"✅ [{title}] 成功转存至专属目录 (共 {len(files)} 个视频文件)"
            else:
                yield f"❌ [{title}] 转存失败: {msg}"
