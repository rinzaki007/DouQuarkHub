import re
import requests
from quark_engine import QuarkEngine

class SearchService:
    def __init__(self, cookie):
        self.cookie = cookie
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

    def search_single_movie_strict(self, title, channels):
        """严格按标题匹配搜寻 TG 频道，避免模糊匹配带来错位资源"""
        if not title or not channels:
            return None, None

        clean_title = title.strip()
        simple_target = re.sub(r'[^\w\u4e00-\u9fa5]', '', clean_title)
        quark_pattern = re.compile(r'(?:pan\.)?quark\.cn/s/([a-zA-Z0-9]+)')

        for ch in channels:
            ch_id = ch.get('id', '').strip() if isinstance(ch, dict) else str(ch).strip()
            ch_name = ch.get('name', ch_id) if isinstance(ch, dict) else ch_id
            if not ch_id:
                continue

            search_url = f"https://t.me/s/{ch_id}?q={requests.utils.quote(clean_title)}"
            try:
                resp = requests.get(search_url, headers=self.headers, timeout=6)
                if resp.status_code != 200:
                    continue

                html = resp.text
                # 提取 TG 消息体文本
                messages = re.findall(r'<div class="tgme_widget_message_text js-message_text.*?">([\s\S]*?)</div>', html)
                
                for msg in messages:
                    plain_text = re.sub(r'<[^>]+>', '', msg)
                    simple_plain = re.sub(r'[^\w\u4e00-\u9fa5]', '', plain_text)

                    # 严格校验：消息文本中必须包含目标名称（防止搜到无关的影片）
                    if clean_title in plain_text or (simple_target and simple_target in simple_plain):
                        matches = quark_pattern.findall(msg)
                        if matches:
                            return matches[0], ch_name
            except Exception:
                continue

        return None, None

    def batch_search_and_transfer_stream(self, movies, channels, target_fid='0', category_fids=None):
        category_fids = category_fids or {}
        engine = QuarkEngine(self.cookie)
        
        yield f"[系统] 🚀 批量转存任务启动，共计处理 {len(movies)} 部影片\n"

        for idx, movie in enumerate(movies, 1):
            title = movie.get('title') if isinstance(movie, dict) else str(movie)
            tag = movie.get('tag', '电影') if isinstance(movie, dict) else '电影'
            
            # 1. 动态识别分类存储目录 FID（如电影、电视剧等）
            parent_fid = category_fids.get(tag, target_fid) if category_fids else target_fid
            if not parent_fid:
                parent_fid = '0'

            yield f"\n----------------------------------------\n"
            yield f"[进度 {idx}/{len(movies)}] 🎬 目标影片: 《{title}》\n"
            yield f"[分类] 🏷️ 识别分类: [{tag}] -> 对应网盘父级 FID: {parent_fid}\n"
            yield f"[检索] 🔍 正在各配置频道中进行严格精准匹配检索...\n"

            pwd_id, found_channel = self.search_single_movie_strict(title, channels)
            if not pwd_id:
                yield f"[检索] ❌ 未能在任何配置频道中找到严格匹配《{title}》的有效夸克资源，跳过此项\n"
                continue

            yield f"[检索] ✅ 严格匹配成功！来源频道: [{found_channel}] | 提取代码: {pwd_id}\n"
            yield f"[解析] 🔎 正在通过夸克引擎穿透解析分享链接详情...\n"

            files, stoken, err = engine.get_share_files(pwd_id)
            if not files:
                yield f"[解析] ❌ 链接解析失败: {err}\n"
                continue

            yield f"[解析] ✨ 成功解析到 {len(files)} 个有效视频文件\n"

            # 2. 自动在分类目录下创建以影片名字命名的专属文件夹
            yield f"[存储] 📁 正在网盘目录 FID [{parent_fid}] 下创建/定位专属文件夹：《{title}》...\n"
            folder_fid = engine.get_or_create_subfolder(title, parent_fid)
            yield f"[存储] 📂 专属文件夹就绪，目标文件夹 FID: {folder_fid}\n"

            files_to_save = [{'fid': f.get('fid')} for f in files if f.get('fid')]
            if not files_to_save:
                yield f"[存储] ⚠️ 链接内未发现可转存的文件 ID\n"
                continue

            yield f"[存储] 📥 正在将文件转存至专属文件夹《{title}》中...\n"
            ok, msg = engine.save_files(pwd_id, files_to_save, stoken, folder_fid)
            
            if ok:
                yield f"[完成] 🎉 《{title}》转存成功！已归档至专属文件夹 (共 {len(files_to_save)} 个文件)\n"
            else:
                yield f"[完成] ❌ 《{title}》转存失败: {msg}\n"
