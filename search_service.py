import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from quark_engine import QuarkEngine

class SearchService:
    def __init__(self, cookie):
        self.cookie = cookie
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

    def search_movie_candidates(self, movie, channels):
        """
        【阶段一：并发搜刮与候选聚合（含详细后端日志）】
        """
        engine = QuarkEngine(self.cookie)
        video_extensions = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.m4v', '.ts', '.m2ts', '.iso')
        
        title = ''
        if isinstance(movie, dict):
            title = movie.get('title', movie.get('name', '')).strip()
        else:
            title = str(movie).strip()

        if not title:
            return []

        clean_title = title
        clean_title = re.sub(r'[\(\（]\s*(19\d{2}|20\d{2})\s*[\)\）]', '', clean_title).strip()
        
        simple_target = re.sub(r'[^\w\u4e00-\u9fa5]', '', clean_title)
        quark_pattern = re.compile(r'(?:pan\.)?quark\.cn/s/([a-zA-Z0-9]+)')

        candidates = []
        seen_pwd_ids = set()

        print(f"[后端检索] 🚀 开始并发搜刮影片: 《{title}》 (清洗后: {clean_title})，共检查 {len(channels)} 个频道")

        def search_single_channel(ch):
            """内部函数：单个频道的检索逻辑（带详细排查日志）"""
            ch_id = ch.get('id', '').strip() if isinstance(ch, dict) else str(ch).strip()
            ch_name = ch.get('name', ch_id) if isinstance(ch, dict) else ch_id
            if not ch_id:
                return []

            local_candidates = []
            search_url = f"https://t.me/s/{ch_id}?q={requests.utils.quote(clean_title)}"
            try:
                resp = requests.get(search_url, headers=self.headers, timeout=5)
                if resp.status_code != 200:
                    print(f"  [频道跳过] 频道 [{ch_name}] (ID: {ch_id}) 请求失败，状态码: {resp.status_code}")
                    return []

                messages = re.findall(r'<div class="tgme_widget_message_text js-message_text.*?">([\s\S]*?)</div>', resp.text)
                
                for msg in messages:
                    plain_text = re.sub(r'<[^>]+>', '', msg)
                    simple_plain = re.sub(r'[^\w\u4e00-\u9fa5]', '', plain_text)

                    if clean_title in plain_text or (simple_target and simple_target in simple_plain):
                        pwd_matches = quark_pattern.findall(msg)
                        
                        for pwd_id in pwd_matches:
                            files, stoken, err = engine.get_share_files(pwd_id)
                            if err or not files:
                                print(f"  [解析提示] 频道 [{ch_name}] 命中短码 {pwd_id} 但获取文件失败: {err}")
                                continue
                            
                            video_files = [
                                {
                                    'fid': f.get('fid'),
                                    'file_name': f.get('file_name', ''),
                                    'size': f.get('size', 0)
                                } 
                                for f in files if any(f.get('file_name', '').lower().endswith(ext) for ext in video_extensions)
                            ]
                            
                            if video_files:
                                first_name = video_files[0]['file_name']
                                print(f"  [有效命中] 🎯 频道 [{ch_name}] 发现资源! 短码: {pwd_id}, 有效视频数: {len(video_files)}, 示例: {first_name}")
                                local_candidates.append({
                                    "channel": ch_name,
                                    "pwd_id": pwd_id,
                                    "stoken": stoken,
                                    "files": video_files,
                                    "summary": f"频道: [{ch_name}] | 包含 {len(video_files)} 个视频 | 示例: {first_name}"
                                })
            except Exception as e:
                print(f"  [频道异常] ❌ 频道 [{ch_name}] 搜刮抛出异常: {str(e)}")
            return local_candidates

        # 使用线程池并发请求所有频道
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(search_single_channel, ch) for ch in channels]
            for future in as_completed(futures):
                try:
                    res = future.result()
                    if res:
                        for cand in res:
                            pwd_id = cand['pwd_id']
                            if pwd_id not in seen_pwd_ids:
                                seen_pwd_ids.add(pwd_id)
                                candidates.append(cand)
                except Exception as e:
                    print(f"[线程池异常] {str(e)}")

        print(f"[后端检索完成] ✅ 《{title}》 最终汇总有效候选资源数: {len(candidates)} 个\n")
        return candidates

    def transfer_selected_resource(self, movie, candidate, target_fid='0', category_fids=None):
        """
        【阶段二：用户选定后执行转存（含详细后端日志）】
        """
        category_fids = category_fids or {}
        engine = QuarkEngine(self.cookie)
        
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

        print(f"[转存服务] 📥 开始处理《{title}》，目标父目录ID: {parent_fid}，来源频道: {candidate.get('channel')}")

        # 1. 创建以电影名命名的专属文件夹
        folder_fid, create_err = engine.get_or_create_subfolder(title, parent_fid)
        if not folder_fid:
            print(f"[转存失败] ❌ 创建专属文件夹失败: {create_err}")
            return False, f"创建专属文件夹失败: {create_err}"

        # 2. 提取选中的文件 ID 列表
        pwd_id = candidate.get('pwd_id')
        stoken = candidate.get('stoken')
        selected_files = candidate.get('files', [])
        
        fid_list = [f.get('fid') for f in selected_files if f.get('fid')]
        if not fid_list:
            print(f"[转存失败] ❌ 所选候选资源中没有有效的视频文件")
            return False, "所选候选资源中没有有效的视频文件"

        # 3. 执行转存
        ok, msg = engine.save_files(pwd_id, [{'fid': fid} for fid in fid_list], stoken, folder_fid)
        if ok:
            print(f"[转存成功] 🎉 《{title}》 成功转存至专属文件夹，短码: {pwd_id}")
            return True, f"《{title}》转存成功！已精准归档至专属文件夹"
        else:
            print(f"[转存失败] ❌ 夸克接口返回错误: {msg}")
            return False, f"转存失败: {msg}"
