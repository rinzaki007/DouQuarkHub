import re
import requests
from quark_engine import QuarkEngine

class SearchService:
    def __init__(self, cookie):
        self.cookie = cookie
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

    def batch_search_and_transfer_stream(self, movies, channels, target_fid='0', category_fids=None):
        category_fids = category_fids or {}
        engine = QuarkEngine(self.cookie)
        
        video_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.m4v', '.ts', '.m2ts', '.iso')

        yield f"[系统] 🚀 批量转存任务正式启动，共计处理 {len(movies)} 部影片\n"

        for idx, movie in enumerate(movies, 1):
            title = ''
            tag = '电影'

            if isinstance(movie, dict):
                title = movie.get('title', movie.get('name', '')).strip()
                tag = movie.get('tag', '电影')
            else:
                title = str(movie).strip()

            parent_fid = category_fids.get(tag, target_fid) if category_fids else target_fid
            if not parent_fid:
                parent_fid = '0'

            yield f"\n----------------------------------------\n"
            yield f"[调试] 收到影片原始数据: {movie}\n"
            yield f"[进度 {idx}/{len(movies)}] 🎬 目标影片: 《{title}》\n"
            yield f"[分类] 🏷 目标分类: [{tag}] (父级网盘 FID: {parent_fid})\n"
            yield f"[检索] 🔍 正在 TG 频道中检索匹配资源...\n"

            valid_pwd_id = None
            valid_files = []
            valid_stoken = ""
            found_channel = ""

            # 过滤掉标题里可能带的括号年份，用于更精准的文字匹配
            clean_title = title
            clean_title = re.sub(r'[\(\（]\s*(19\d{2}|20\d{2})\s*[\)\）]', '', clean_title).strip()
            
            simple_target = re.sub(r'[^\w\u4e00-\u9fa5]', '', clean_title)
            quark_pattern = re.compile(r'(?:pan\.)?quark\.cn/s/([a-zA-Z0-9]+)')

            for ch in channels:
                ch_id = ch.get('id', '').strip() if isinstance(ch, dict) else str(ch).strip()
                ch_name = ch.get('name', ch_id) if isinstance(ch, dict) else ch_id
                if not ch_id:
                    continue

                yield f"[检索] 📡 正在频道 [{ch_name}] 中检索关键词: \"{clean_title}\"...\n"
                search_url = f"https://t.me/s/{ch_id}?q={requests.utils.quote(clean_title)}"
                try:
                    resp = requests.get(search_url, headers=self.headers, timeout=6)
                    if resp.status_code != 200:
                        yield f"[检索] ⚠️ 频道 [{ch_name}] 请求失败 (HTTP {resp.status_code})\n"
                        continue

                    messages = re.findall(r'<div class="tgme_widget_message_text js-message_text.*?">([\s\S]*?)</div>', resp.text)
                    yield f"[检索] 📄 频道 [{ch_name}] 共抓取到 {len(messages)} 条相关消息，开始比对...\n"
                    
                    for msg in messages:
                        plain_text = re.sub(r'<[^>]+>', '', msg)
                        simple_plain = re.sub(r'[^\w\u4e00-\u9fa5]', '', plain_text)

                        # 只要名字对得上，就提取分享链接
                        if clean_title in plain_text or (simple_target and simple_target in simple_plain):
                            pwd_matches = quark_pattern.findall(msg)
                            
                            for pwd_id in pwd_matches:
                                files, stoken, err = engine.get_share_files(pwd_id)
                                if err:
                                    continue
                                
                                if files:
                                    # 提取所有视频文件，不再做任何年份拦截限制
                                    video_files = [f for f in files if any(f.get('file_name', '').lower().endswith(ext) for ext in video_extensions)]
                                    
                                    if video_files:
                                        valid_pwd_id = pwd_id
                                        valid_files = video_files
                                        valid_stoken = stoken
                                        found_channel = ch_name
                                        yield f"[检索] ✅ 命中目标！在频道 [{ch_name}] 找到匹配的视频源（共 {len(video_files)} 个文件）\n"
                                        break
                        if valid_pwd_id:
                            break
                except Exception as e:
                    yield f"[检索] ❌ 频道 [{ch_name}] 检索异常: {str(e)}\n"
                    continue
                if valid_pwd_id:
                    break

            if not valid_pwd_id:
                yield f"[检索] ❌ 未能在任何配置频道中找到《{title}》的资源\n"
                continue

            # 创建专属文件夹并转存
            yield f"[存储] 📁 正在父级网盘目录 [{parent_fid}] 下创建专属文件夹：《{title}》...\n"
            folder_fid, create_err = engine.get_or_create_subfolder(title, parent_fid)
            
            if not folder_fid:
                yield f"[存储] ❌ 创建专属文件夹失败: {create_err}\n"
                continue
            
            files_to_save = [{'fid': f.get('fid')} for f in valid_files if f.get('fid')]
            yield f"[存储] 📥 正在将 {len(files_to_save)} 个视频文件转存至专属文件夹中...\n"
            
            ok, msg = engine.save_files(valid_pwd_id, files_to_save, valid_stoken, folder_fid)
            if ok:
                yield f"[完成] 🎉 《{title}》转存成功！文件已全部归档\n"
            else:
                yield f"[完成] ❌ 《{title}》转存失败: {msg}\n"
