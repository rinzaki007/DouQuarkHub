import re
import requests
from quark_engine import QuarkEngine

class SearchService:
    def __init__(self, cookie):
        self.cookie = cookie
        self.engine = QuarkEngine(cookie)

    def search_tg_channel(self, channel_id, keyword):
        """从 Telegram 频道公开 Web 页检索夸克分享链接"""
        url = f"https://t.me/s/{channel_id}?q={requests.utils.quote(keyword)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        links = []
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                # 提取夸克网盘链接中的 pwd_id
                found = re.findall(r'https://pan\.quark\.cn/s/([a-zA-Z0-9]+)', resp.text)
                for pwd_id in found:
                    if pwd_id not in links:
                        links.append(pwd_id)
        except Exception as e:
            pass
        return links

    def batch_search_and_transfer(self, movies, channels, target_fid='0'):
        """批量检索频道并自动转存到夸克网盘"""
        results = {}
        
        for movie in movies:
            logs = []
            logs.append(f"🔍 开始检索资源: {movie}")
            found_links = []

            # 1. 遍历 Telegram 频道检索
            for ch in channels:
                ch_name = ch.get('name', '未命名频道')
                ch_id = ch.get('id', '')
                if not ch_id:
                    continue
                
                p_ids = self.search_tg_channel(ch_id, movie)
                if p_ids:
                    logs.append(f"  └─ 频道 [{ch_name}] 命中 {len(p_ids)} 个夸克资源")
                    for p_id in p_ids:
                        if p_id not in found_links:
                            found_links.append(p_id)

            if not found_links:
                logs.append("  ❌ 遍历全部指定频道，未检索到匹配的夸克分享链接")
                results[movie] = logs
                continue

            # 2. 尝试转存命中的资源
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
