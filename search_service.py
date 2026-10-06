import re
import requests
from quark_engine import QuarkEngine

class SearchService:
    def __init__(self, cookie):
        self.cookie = cookie
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

    def _fetch_year_from_url(self, url):
        """通过豆瓣等详情页 URL 自动抓取年份"""
        if not url or 'douban.com' not in url:
            return ''
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://movie.douban.com/'
            }
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                html_text = resp.text
                # 1. 尝试匹配豆瓣的 v:initialReleaseDate 标签
                m = re.search(r'v:initialReleaseDate.*?content="(\d{4})', html_text)
                if m:
                    return m.group(1)
                
                # 2. 尝试从前序文本中匹配合法的电影年份 (20xx 或 19xx)
                all_years = re.findall(r'\b(20\d{2}|19\d{2})\b', html_text[:3000])
                for y in all_years:
                    if 1950 <= int(y) <= 2030:
                        return y
        except Exception:
            pass
        return ''

    def batch_search_and_transfer_stream(self, movies, channels, target_fid='0', category_fids=None):
        category_fids = category_fids or {}
        engine = QuarkEngine(self.cookie)
        
        video_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.m4v', '.ts', '.m2ts', '.iso')

        yield f"[系统] 🚀 批量转存任务正式启动, 共计处理 {len(movies)} 部影片\n"

        for idx, movie in enumerate(movies, 1):
            target_year = ''
            title = ''
            tag = '电影'
            url = ''

            if isinstance(movie, dict):
                title = movie.get('title', movie.get('name', '')).strip()
                tag = movie.get('tag', '电影')
                url = movie.get('url', '')
                
                # 1. 优先尝试从豆瓣链接网页中提取真实年份
                if url:
                    target_year = self._fetch_year_from_url(url)
                
                # 2. 如果没抓到，尝试从数据字典其他字段提取
                if not target_year:
                    for k, v in movie.items():
                        if k not in ['title', 'name', 'cover', 'url'] and v:
                            m_y = re.search(r'\b(19\d{2}|20\d{2})\b', str(v))
                            if m_y:
                                target_year = m_y.group(1)
                                break
                
                # 3. 尝试从标题括号中提取
                if not target_year:
                    title_year_match = re.search(r'[\(\（]\s*(19\d{2}|20\d{2})\s*[\)\）]', title)
                    if title_year_match:
                        target_year = title_year_match.group(1)
            else:
                title = str(movie).strip()
                title_year_match = re.search(r'[\(\（]\s*(19\d{2}|20\d{2})\s*[\)\）]', title)
                if title_year_match:
                    target_year = title_year_match.group(1)

            parent_fid = category_fids.get(tag, target_fid) if category_fids else target_fid
            if not parent_fid:
                parent_fid = '0'

            yield f"\n----------------------------------------\n"
            yield f"[调试] 收到影片原始数据: {movie}\n"
            yield f"[进度 {idx}/{len(movies)}] 🎬 目标影片: 《{title}》 | 豆瓣链接解析年份: 【{target_year or '未识别到'}】\n"
            yield f"[分类] 🏷 目标分类: [{tag}] (父级网盘 FID: {parent_fid})\n"
            yield f"[检索] 🔍 正在 TG 频道中进行严格标题与年份甄别...\n"

            valid_pwd_id = None
            valid_files = []
            valid_stoken = ""
            found_channel = ""

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
                    yield f"[检索] 📄 频道 [{ch_name}] 共抓取到 {len(messages)} 条相关消息，开始逐条比对...\n"
                    
                    for msg in messages:
                        plain_text = re.sub(r'<[^>]+>', '', msg)
                        simple_plain = re.sub(r'[^\w\u4e00-\u9fa5]', '', plain_text)

                        if clean_title in plain_text or (simple_target and simple_target in simple_plain):
                            pwd_matches = quark_pattern.findall(msg)
                            
                            for pwd_id in pwd_matches:
                                files, stoken, err = engine.get_share_files(pwd_id)
                                if err:
                                    continue
                                
                                if files:
                                    video_files = [f for f in files if any(f.get('file_name', '').lower().endswith(ext) for ext in video_extensions)]
                                    
                                    matched_video_files = []
                                    for vf in video_files:
                                        fname = vf.get('file_name', '')
                                        file_year_match = re.search(r'(19\d{2}|20\d{2})', fname)
                                        file_year = file_year_match.group(1) if file_year_match else ''
                                        
                                        yield f"   * 扫描文件: {fname} (文件自带年份: {file_year or '无'})\n"
                                        
                                        # 【严格年份校验】
                                        if target_year:
                                            if file_year and file_year != target_year:
                                                yield f"     ❌ 【年份拦截】目标年份是 [{target_year}]，而该文件是 [{file_year}]，已安全拦截！\n"
                                                continue
                                            elif not file_year:
                                                yield f"     ⚠️ 【年份警告】文件未检测到明确年份标识\n"
                                        
                                        matched_video_files.append(vf)

                                    if matched_video_files:
                                        valid_pwd_id = pwd_id
                                        valid_files = matched_video_files
                                        valid_stoken = stoken
                                        found_channel = ch_name
                                        yield f"[检索] ✅ 校验通过！在频道 [{ch_name}] 锁定符合年份要求的视频源（共 {len(matched_video_files)} 个文件）\n"
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

            # 2. 创建专属文件夹并转存
            yield f"[存储] 📁 正在父级网盘目录 [{parent_fid}] 下创建专属文件夹：《{title}》...\n"
            folder_fid, create_err = engine.get_or_create_subfolder(title, parent_fid)
            
            if not folder_fid:
                yield f"[存储] ❌ 创建专属文件夹失败: {create_err}\n"
                continue
            
            files_to_save = [{'fid': f.get('fid')} for f in valid_files if f.get('fid')]
            yield f"[存储] 📥 正在将 {len(files_to_save)} 个视频文件转存至专属文件夹中...\n"
            
            ok, msg = engine.save_files(valid_pwd_id, files_to_save, valid_stoken, folder_fid)
            if ok:
                yield f"[完成] 🎉 《{title}》转存成功！视频文件已精准归档\n"
            else:
                yield f"[完成] ❌ 《{title}》转存失败: {msg}\n"
