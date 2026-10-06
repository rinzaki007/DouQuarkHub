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
            # 兼容处理电影对象或纯字符串
            if isinstance(movie, dict):
                title = movie.get('title', '').strip()
                tag = movie.get('tag', '电影')
                # 提取目标电影年份（支持 year 或 release_date 字段）
                raw_year = str(movie.get('year') or movie.get('release_date') or '')
                year_match = re.search(r'(20\d{2}|19\d{2})', raw_year)
                target_year = year_match.group(1) if year_match else ''
            else:
                title = str(movie).strip()
                tag = '电影'
                target_year = ''

            parent_fid = category_fids.get(tag, target_fid) if category_fids else target_fid
            if not parent_fid:
                parent_fid = '0'

            yield f"\n----------------------------------------\n"
            yield f"[进度 {idx}/{len(movies)}] 🎬 目标影片: 《{title}》 (目标年份: {target_year or '未指定'})\n"
            yield f"[分类] 🏷 目标分类: [{tag}] (父级网盘 FID: {parent_fid})\n"
            yield f"[检索] 🔍 正在 TG 频道中进行严格标题与年份甄别...\n"

            valid_pwd_id = None
            valid_files = []
            valid_stoken = ""
            found_channel = ""

            clean_title = title
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
                    yield f"[检索] 📄 频道 [{ch_name}] 共抓取到 {len(messages)} 条相关消息，开始逐条比对...\n"
                    
                    for msg in messages:
                        plain_text = re.sub(r'<[^>]+>', '', msg)
                        simple_plain = re.sub(r'[^\w\u4e00-\u9fa5]', '', plain_text)

                        # 标题匹配判断
                        if clean_title in plain_text or (simple_target and simple_target in simple_plain):
                            pwd_matches = quark_pattern.findall(msg)
                            if pwd_matches:
                                yield f"[检索] 🔗 命中标题消息！发现 {len(pwd_matches)} 个夸克链接，正在解析文件...\n"
                            
                            for pwd_id in pwd_matches:
                                files, stoken, err = engine.get_share_files(pwd_id)
                                if err:
                                    yield f"[检索] ⚠️ 解析分享链接 {pwd_id} 失败: {err}\n"
                                    continue
                                
                                if files:
                                    video_files = [f for f in files if any(f.get('file_name', '').lower().endswith(ext) for ext in video_extensions)]
                                    yield f"[检索] 📁 分享链接内共找到 {len(files)} 个文件，其中有效视频文件 {len(video_files)} 个：\n"
                                    
                                    # 逐个视频文件进行年份过滤与详细日志打印
                                    matched_video_files = []
                                    for vf in video_files:
                                        fname = vf.get('file_name', '')
                                        # 从文件名中提取年份 (19xx 或 20xx)
                                        file_year_match = re.search(r'(19\d{2}|20\d{2})', fname)
                                        file_year = file_year_match.group(1) if file_year_match else ''
                                        
                                        yield f"   * 文件: {fname} (解析年份: {file_year or '无'})\n"
                                        
                                        # 如果目标电影指定了年份，严格把关
                                        if target_year:
                                            if file_year and file_year != target_year:
                                                yield f"     ❌ 年份不匹配！目标要求为 [{target_year}]，而文件标识为 [{file_year}]，已自动过滤\n"
                                                continue
                                            elif not file_year:
                                                yield f"     ⚠️ 文件名中未检测到明确年份，按保险策略跳过或谨慎放行\n"
                                                continue
                                        
                                        matched_video_files.append(vf)

                                    if matched_video_files:
                                        valid_pwd_id = pwd_id
                                        valid_files = matched_video_files
                                        valid_stoken = stoken
                                        found_channel = ch_name
                                        yield f"[检索] ✅ 校验通过！在频道 [{ch_name}] 精准锁定符合年份要求的视频源（共 {len(matched_video_files)} 个文件）\n"
                                        break
                        if valid_pwd_id:
                            break
                except Exception as e:
                    yield f"[检索] ❌ 频道 [{ch_name}] 检索异常: {str(e)}\n"
                    continue
                if valid_pwd_id:
                    break

            if not valid_pwd_id:
                yield f"[检索] ❌ 未能在任何配置频道中找到符合条件（标题吻合且年份相符: {target_year or '无限制'}）的《{title}》资源\n"
                continue

            # 2. 在对应的分类目录下创建以影片名字命名的专属文件夹
            yield f"[存储] 📁 正在父级网盘目录 [{parent_fid}] 下创建专属文件夹：《{title}》...\n"
            folder_fid, create_err = engine.get_or_create_subfolder(title, parent_fid)
            
            if not folder_fid:
                yield f"[存储] ❌ 创建专属文件夹《{title}》失败，详细原因: {create_err}，终止转存\n"
                continue
            
            yield f"[存储] 📂 专属文件夹创建成功！目标文件夹 FID: {folder_fid}\n"

            files_to_save = [{'fid': f.get('fid')} for f in valid_files if f.get('fid')]
            yield f"[存储] 📥 正在将 {len(files_to_save)} 个视频文件转存至专属文件夹中...\n"
            
            ok, msg = engine.save_files(valid_pwd_id, files_to_save, valid_stoken, folder_fid)
            if ok:
                yield f"[完成] 🎉 《{title}》转存成功！视频文件已精准归档至专属文件夹中\n"
            else:
                yield f"[完成] ❌ 《{title}》转存失败: {msg}\n"
