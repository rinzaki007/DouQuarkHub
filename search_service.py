import requests
import re
from quark_engine import QuarkEngine

class SearchService:
    def __init__(self, cookie):
        self.cookie = cookie
        self.engine = QuarkEngine(cookie)

    def search_single_movie(self, title, channels):
        """
        在指定的 TG 频道列表中严格检索包含 title 的消息
        返回: (pwd_id, channel_name)
        """
        cleaned_title = title.strip()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        for ch in channels:
            ch_id = ch.get('id', '').strip().replace('@', '')
            ch_name = ch.get('name', ch_id)
            if not ch_id:
                continue

            url = f"https://t.me/s/{ch_id}"
            try:
                resp = requests.get(url, headers=headers, timeout=5)
                if resp.status_code != 200:
                    continue

                html = resp.text
                
                # 尝试抓取频道真实标题
                title_match = re.search(r'<div class="tgme_channel_info_title"><span dir="auto">(.*?)</span></div>', html)
                if title_match:
                    ch_name = title_match.group(1).strip()

                # 提取 Telegram 消息文本块
                messages = re.findall(r'<div class="tgme_widget_message_text js-message_text".*?>([\s\S]*?)</div>', html)
                
                # 倒序检索最新的消息
                for msg in reversed(messages):
                    # 清除 HTML 标签获取纯文本
                    clean_text = re.sub(r'<[^>]+>', '', msg)

                    # 🎯 核心改动 1：严格匹配 - 消息中必须精确包含选择的资源完整名称
                    if cleaned_title in clean_text:
                        # 提取夸克分享码
                        pwd_match = re.search(r'pan\.quark\.cn/s/([a-zA-Z0-9]+)', msg)
                        if pwd_match:
                            pwd_id = pwd_match.group(1)
                            return pwd_id, ch_name
            except Exception as e:
                print(f"检索频道 [{ch_name}] 失败: {e}")
                continue

        return None, None

    def batch_search_and_transfer_stream(self, movies, channels, target_fid='0'):
        """
        批量检索与转存流式输出日志
        """
        yield f"[系统] 🚀 开始处理批量转存，共 {len(movies)} 个目标..."

        for idx, movie in enumerate(movies, 1):
            title = movie.get('title', '').strip()
            yield f"\n[系统] 🔍 [{idx}/{len(movies)}] 正在检索：《{title}》..."

            pwd_id, ch_name = self.search_single_movie(title, channels)

            if not pwd_id:
                yield f"[系统] ❌ 未能在已有频道中找到《{title}》的有效夸克资源"
                continue

            # 🎯 核心改动 2：清晰输出来源频道名称与夸克分享代码
            yield f"[系统] 📢 [来源频道: {ch_name}] 成功精确命中《{title}》 | 夸克代码: {pwd_id}"
            yield f"[系统] 🔎 正在穿透解析资源内容..."

            files, stoken, err = self.engine.get_share_files(pwd_id, only_video=True)
            if not files:
                yield f"[系统] ⚠️ 链接解析失败或未包含有效视频文件: {err}"
                continue

            # 🎯 核心改动 3：自动在目标目录下新建“资源名称专属文件夹”
            yield f"[系统] 📁 正在目标目录下创建/定位专属文件夹：《{title}》..."
            movie_folder_fid = self.engine.get_or_create_subfolder(title, target_fid)

            if not movie_folder_fid:
                yield f"[系统] ❌ 创建专属文件夹失败，跳过转存"
                continue

            files_to_save = [{'fid': f['fid']} for f in files]
            ok, msg = self.engine.save_files(pwd_id, files_to_save, stoken, movie_folder_fid)

            if ok:
                yield f"[系统] ✅ 《{title}》已成功转存至专属文件夹《{title}》中！(共 {len(files)} 个视频文件)"
            else:
                yield f"[系统] ❌ 转存失败: {msg}"
