import requests
import re
from urllib.parse import quote
from quark_engine import QuarkEngine

class SearchService:
    def __init__(self, cookie):
        self.cookie = cookie
        self.engine = QuarkEngine(cookie)

    def search_single_movie(self, title, channels):
        """在指定的 TG 频道列表中精准检索资源"""
        cleaned_title = title.strip()
        simplified_title = re.sub(r'[^\w\u4e00-\u9fa5]', '', cleaned_title)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        for ch in channels:
            if isinstance(ch, dict):
                ch_id = ch.get('id', '').strip().replace('@', '')
                ch_name = ch.get('name', ch_id)
            else:
                ch_id = str(ch).strip().replace('@', '')
                ch_name = ch_id

            if not ch_id:
                continue

            # 开启频道历史搜索
            urls_to_try = [
                f"https://t.me/s/{ch_id}?q={quote(cleaned_title)}",
                f"https://t.me/s/{ch_id}"
            ]

            for url in urls_to_try:
                try:
                    resp = requests.get(url, headers=headers, timeout=6)
                    if resp.status_code != 200:
                        continue

                    html = resp.text
                    
                    title_match = re.search(r'<div class="tgme_channel_info_title"><span dir="auto">(.*?)</span></div>', html)
                    if title_match:
                        ch_name = title_match.group(1).strip()

                    messages = re.findall(r'<div class="tgme_widget_message_text js-message_text".*?>([\s\S]*?)</div>', html)
                    
                    for msg in reversed(messages):
                        clean_text = re.sub(r'<[^>]+>', '', msg)
                        clean_text_simple = re.sub(r'[^\w\u4e00-\u9fa5]', '', clean_text)

                        if cleaned_title in clean_text or (simplified_title and simplified_title in clean_text_simple):
                            pwd_match = re.search(r'pan\.quark\.cn/s/([a-zA-Z0-9]+)', msg)
                            if pwd_match:
                                pwd_id = pwd_match.group(1)
                                return pwd_id, ch_name
                except Exception as e:
                    print(f"检索频道 [{ch_name}] 异常: {e}")
                    continue

        return None, None

    def batch_search_and_transfer_stream(self, movies, channels, target_fid='0', category_fids=None):
        category_fids = category_fids or {}
        yield f"[系统] 🚀 开始处理批量转存，共 {len(movies)} 个目标...\n"

        for idx, movie in enumerate(movies, 1):
            title = movie.get('title', '').strip()
            tag = movie.get('tag', '电影')
            
            parent_fid = category_fids.get(tag, target_fid) if category_fids else target_fid
            if not parent_fid:
                parent_fid = '0'

            yield f"\n[系统] 🔍 [{idx}/{len(movies)}] 正在检索：《{title}》（分类: {tag}）...\n"

            pwd_id, ch_name = self.search_single_movie(title, channels)

            if not pwd_id:
                yield f"[系统] ❌ 未能在已配置频道中找到《{title}》的有效夸克资源\n"
                continue

            yield f"[系统] 📢 [来源频道: {ch_name}] 精确命中《{title}》 | 夸克代码: {pwd_id}\n"
            yield f"[系统] 🔎 正在穿透解析资源内容...\n"

            files, stoken, err = self.engine.get_share_files(pwd_id, only_video=True)
            if not files:
                yield f"[系统] ⚠️ 资源解析失败或未包含有效视频: {err}\n"
                continue

            yield f"[系统] 📁 正在专属存储目录下新建/定位文件夹：《{title}》...\n"
            movie_folder_fid = self.engine.get_or_create_subfolder(title, parent_fid)

            files_to_save = [{'fid': f['fid']} for f in files]
            ok, msg = self.engine.save_files(pwd_id, files_to_save, stoken, movie_folder_fid)

            if ok:
                yield f"[系统] ✅ 《{title}》已成功转存至专属文件夹《{title}》中！(共 {len(files)} 个视频文件)\n"
            else:
                yield f"[系统] ❌ 转存失败: {msg}\n"
