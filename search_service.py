import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from quark_engine import QuarkEngine

class SearchService:
    def __init__(self, cookie):
        self.cookie = cookie
        self.engine = QuarkEngine(cookie)

    def search_single_tg_channel(self, channel, keyword):
        """单频道检索，超时设为 3 秒防止挂起"""
        ch_name = channel.get('name', '未命名频道')
        ch_id = channel.get('id', '').strip()
        if not ch_id:
            return ch_name, []

        url = f"https://t.me/s/{ch_id}?q={requests.utils.quote(keyword)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        found_links = []
        try:
            resp = requests.get(url, headers=headers, timeout=3)
            if resp.status_code == 200:
                found = re.findall(r'https://pan\.quark\.cn/s/([a-zA-Z0-9]+)', resp.text)
                for pwd_id in found:
                    if pwd_id not in found_links:
                        found_links.append(pwd_id)
        except Exception:
            pass
        return ch_name, found_links

    def batch_search_and_transfer(self, movies, channels, target_fid='0'):
        """多线程并发极速检索频道 + 转存"""
        results = {}
        
        for movie in movies:
            logs = []
            logs.append(f"🔍 开始检索资源: {movie}")
            found_links = []

            # 多线程并发查询多频道，极速完成，不给反向代理超时的机会
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_ch = {
                    executor.submit(self.search_single_tg_channel, ch, movie): ch 
                    for ch in channels
                }
                for future in as_completed(future_to_ch):
                    ch_name, p_ids = future.result()
                    if p_ids:
                        logs.append(f"  └─ 频道 [{ch_name}] 命中 {len(p_ids)} 个夸克资源")
                        for p_id in p_ids:
                            if p_id not in found_links:
                                found_links.append(p_id)

            if not found_links:
                logs.append("  ❌ 遍历全部指定频道，未检索到匹配的夸克分享链接")
                results[movie] = logs
                continue

            transfer_success = False
            for pwd_id in found_links:
                logs.append(f"  🚀 正在解析并尝试转存链接 (ID: {pwd_id})...")
                
                files, stoken, share_id = self.engine.get_share_files(pwd_id)
                if not files:
                    logs.append("     └─ ⚠️ 链接解析失败或分享已被取消/失效")
                    continue

                fids = [f['fid'] for f in files]
                ok, msg = self.engine.save_files(fids, target_fid, share_id, stoken)
                if ok:
                    logs.append(f"     └─ ✅ 转存成功！已保存至目标目录 (FID: {target_fid})")
                    transfer_success = True
                    break
                else:
                    logs.append(f"     └─ ❌ 转存失败: {msg}")

            if not transfer_success:
                logs.append("  ⚠️ 所有命中的资源链接转存均未成功")

            results[movie] = logs

        return results
