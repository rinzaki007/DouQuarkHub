import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from quark_engine import QuarkEngine

class SearchService:
    def __init__(self, cookie):
        self.cookie = cookie
        self.engine = QuarkEngine(cookie)

    def search_single_tg_channel(self, channel, keyword):
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
            resp = requests.get(url, headers=headers, timeout=2.0)
            if resp.status_code == 200:
                found = re.findall(r'https://pan\.quark\.cn/s/([a-zA-Z0-9]+)', resp.text)
                for pwd_id in found:
                    if pwd_id not in found_links:
                        found_links.append(pwd_id)
        except Exception:
            pass
        return ch_name, found_links

    def batch_search_and_transfer_stream(self, movies, channels, target_fid='0'):
        for movie in movies:
            yield f"\n--- [ {movie} ] ---"
            yield f"🔍 开始检索资源: {movie}"
            found_links = []

            workers = max(1, min(len(channels), 15))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_to_ch = {
                    executor.submit(self.search_single_tg_channel, ch, movie): ch 
                    for ch in channels
                }
                for future in as_completed(future_to_ch):
                    try:
                        ch_name, p_ids = future.result()
                        if p_ids:
                            yield f"  └─ 频道 [{ch_name}] 命中 {len(p_ids)} 个夸克资源"
                            for p_id in p_ids:
                                if p_id not in found_links:
                                    found_links.append(p_id)
                    except Exception:
                        pass

            if not found_links:
                yield "  ❌ 遍历全部指定频道，未检索到匹配的夸克分享链接"
                continue

            transfer_success = False
            for pwd_id in found_links:
                yield f"  🚀 解析资源 (ID: {pwd_id})..."
                
                files, stoken, err_msg = self.engine.get_share_files(pwd_id)
                if not files or not stoken:
                    yield f"     └─ ⚠️ 解析失败: {err_msg or '链接已失效'}"
                    continue

                ok, msg = self.engine.save_files(pwd_id, files, stoken, target_fid)
                if ok:
                    yield f"     └─ ✅ 转存成功！已保存至目录 (FID: {target_fid})"
                    transfer_success = True
                    break
                else:
                    yield f"     └─ ❌ 转存失败: {msg}"

            if not transfer_success:
                yield "  ⚠️ 所有命中的资源链接均未转存成功"

        yield "\n✨ 本轮任务全部执行完成！"
