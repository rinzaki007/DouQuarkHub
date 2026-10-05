import re
import requests
from quark_engine import QuarkEngine

class SearchService:
    def __init__(self, cookie):
        self.cookie = cookie
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

    def search_single_movie_pwd_id(self, title, channels):
        """在已配置的 TG 频道中检索指定剧名，提取第一个有效的夸克链接 pwd_id"""
        if not title or not channels:
            return None

        # 匹配夸克分享链接中的 pwd_id (如 pan.quark.cn/s/ef7951063756)
        quark_pattern = re.compile(r'(?:pan\.)?quark\.cn/s/([a-zA-Z0-9]+)')

        for ch in channels:
            ch_id = ch.get('id', '').strip()
            if not ch_id:
                continue

            # 请求 Telegram 频道网页预览版的搜索接口
            search_url = f"https://t.me/s/{ch_id}?q={requests.utils.quote(title)}"
            try:
                resp = requests.get(search_url, headers=self.headers, timeout=6)
                if resp.status_code == 200:
                    matches = quark_pattern.findall(resp.text)
                    if matches:
                        return matches[0]
            except Exception:
                continue

        return None

    def batch_search_and_transfer_stream(self, movies, channels, target_fid='0'):
        """批量检索并转存流式日志输出"""
        engine = QuarkEngine(self.cookie)
        for title in movies:
            yield f"🔍 正在检索: [{title}]..."
            pwd_id = self.search_single_movie_pwd_id(title, channels)
            if not pwd_id:
                yield f"❌ 未在配置频道中找到 [{title}] 的夸克资源"
                continue

            yield f"🟢 找到资源链接 ID: {pwd_id}，正在解析内容..."
            files, stoken, err = engine.get_share_files(pwd_id)
            if not files:
                yield f"❌ 解析分享链接失败: {err}"
                continue

            files_to_save = [{'fid': f.get('fid')} for f in files if f.get('fid')]
            if not files_to_save:
                yield f"⚠️ [{title}] 链接内未发现可转存的文件"
                continue

            ok, msg = engine.save_files(pwd_id, files_to_save, stoken, target_fid)
            if ok:
                yield f"✅ [{title}] 成功转存至目标目录 (共 {len(files_to_save)} 个文件)"
            else:
                yield f"❌ [{title}] 转存失败: {msg}"
