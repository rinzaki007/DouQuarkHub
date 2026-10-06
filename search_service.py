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
        
        # 🎯 严格的视频格式白名单（彻底拒绝 flac、mp3 音频和散乱杂质文件）
        video_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.m4v', '.ts', '.m2ts', '.iso')

        yield f"[系统] 🚀 批量转存任务正式启动，共计处理 {len(movies)} 部影片\n"

        for idx, movie in enumerate(movies, 1):
            title = movie.get('title') if isinstance(movie, dict) else str(movie)
            tag = movie.get('tag', '电影') if isinstance(movie, dict) else '电影'
            
            # 1. 动态获取分类对应的父级网盘 FID
            parent_fid = category_fids.get(tag, target_fid) if category_fids else target_fid
            if not parent_fid:
                parent_fid = '0'

            yield f"\n----------------------------------------\n"
            yield f"[进度 {idx}/{len(movies)}] 🎬 目标影片: 《{title}》\n"
            yield f"[分类] 🏷️️ 目标分类: [{tag}] (父级网盘 FID: {parent_fid})\n"
            yield f"[检索] 🔍 正在 TG 频道中进行严格标题匹配与资源有效性甄别...\n"

            valid_pwd_id = None
            valid_files = []
            valid_stoken = ""
            found_channel = ""

            clean_title = title.strip()
            simple_target = re.sub(r'[^\w\u4e00-\u9fa5]', '', clean_title)
            quark_pattern = re.compile(r'(?:pan\.)?quark\.cn/s/([a-zA-Z0-9]+)')

            # 遍历所有配置的频道
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

                    messages = re.findall(r'<div class="tgme_widget_message_text js-message_text.*?">([\s\S]*?)</div>', resp.text)
                    for msg in messages:
                        plain_text = re.sub(r'<[^>]+>', '', msg)
                        simple_plain = re.sub(r'[^\w\u4e00-\u9fa5]', '', plain_text)

                        # 严格标题比对
                        if clean_title in plain_text or (simple_target and simple_target in simple_plain):
                            pwd_matches = quark_pattern.findall(msg)
                            for pwd_id in pwd_matches:
                                yield f"[检索] 🔎 在频道 [{ch_name}] 发现链接 [{pwd_id}]，正在穿透解析并检查是否为视频文件...\n"
                                files, stoken, err = engine.get_share_files(pwd_id)
                                
                                if files:
                                    # 过滤出真正的视频文件，直接剔除音频（flac/mp3等）与压缩包
                                    video_files = [f for f in files if any(f.get('file_name', '').lower().endswith(ext) for ext in video_extensions)]
                                    
                                    if video_files:
                                        valid_pwd_id = pwd_id
                                        valid_files = video_files
                                        valid_stoken = stoken
                                        found_channel = ch_name
                                        yield f"[检索] ✅ 验证通过！精准锁定有效视频源（共 {len(video_files)} 个视频文件）\n"
                                        break
                                    else:
                                        yield f"[检索] ⚠️ 该链接内不包含视频文件（可能为原声带/音频专辑/小说），已自动跳过并继续寻找...\n"
                        if valid_pwd_id:
                            break
                except Exception:
                    continue
                if valid_pwd_id:
                    break

            if not valid_pwd_id:
                yield f"[检索] ❌ 未能在任何配置频道中找到包含有效视频的《{title}》资源\n"
                continue

            # 2. 在对应的分类目录下创建以影片名字命名的专属文件夹
            yield f"[存储] 📁 正在父级网盘目录 [{parent_fid}] 下创建专属文件夹：《{title}》...\n"
            folder_fid = engine.get_or_create_subfolder(title, parent_fid)
            
            if not folder_fid:
                yield f"[存储] ❌ 创建专属文件夹《{title}》失败，终止转存\n"
                continue
            
            yield f"[存储] 📂 专属文件夹创建成功！目标文件夹 FID: {folder_fid}\n"

            files_to_save = [{'fid': f.get('fid')} for f in valid_files if f.get('fid')]
            yield f"[存储] 📥 正在将 {len(files_to_save)} 个视频文件转存至专属文件夹中...\n"
            
            ok, msg = engine.save_files(valid_pwd_id, files_to_save, valid_stoken, folder_fid)
            if ok:
                yield f"[完成] 🎉 《{title}》转存成功！视频文件已精准归档至专属文件夹中\n"
            else:
                yield f"[完成] ❌ 《{title}》转存失败: {msg}\n"
