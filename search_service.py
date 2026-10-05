import re
import requests
import urllib.parse
from utils import load_channels
from quark_engine import QuarkEngine

def find_quark_links_for_movie(movie_name, channels):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    encoded_name = urllib.parse.quote(movie_name)
    candidates = []
    seen_codes = set()

    for channel in channels:
        ch_name = channel.get("name", "")
        ch_id = channel.get("id", "")
        if not ch_id:
            continue
            
        tg_url = f"https://t.me/s/{ch_id}?q={encoded_name}"
        try:
            res = requests.get(tg_url, headers=headers, timeout=5)
            if res.status_code == 200:
                text = res.text
                posts = re.findall(r'<div class="tgme_widget_message_text[^>]*>(.*?)</div>', text, re.DOTALL)
                for post in posts:
                    clean_post = re.sub(r'<[^>]+>', '', post)
                    if movie_name in clean_post:
                        matches = re.findall(r"quark\.cn/s/([a-zA-Z0-9]+)", post)
                        for code in matches:
                            if code not in seen_codes:
                                seen_codes.add(code)
                                candidates.append((ch_name, code))
        except Exception:
            pass

    yiso_url = f"https://yiso.fun/api/search?q={encoded_name}&page=1"
    try:
        res = requests.get(yiso_url, headers=headers, timeout=5)
        if res.status_code == 200:
            try:
                data = res.json()
                results = data.get("data", {}).get("list", []) or data.get("list", [])
                for item in results:
                    title = str(item.get("title", "") or item.get("name", ""))
                    if movie_name in title:
                        matches = re.findall(r"quark\.cn/s/([a-zA-Z0-9]+)", str(item))
                        for code in matches:
                            if code not in seen_codes:
                                seen_codes.add(code)
                                candidates.append(("易搜备用源", code))
            except Exception:
                pass
    except Exception:
        pass

    return candidates

def execute_transfer_logic(movie_name, quark_cookie, target_folder_id):
    channels = load_channels()
    logs = [f"[{movie_name}] 🔄 正在通过设定的 {len(channels)} 个频道检索资源..."]
    
    engine = QuarkEngine(quark_cookie)
    is_valid, auth_result = engine.check_auth()
    if not is_valid:
        return [f"[{movie_name}] ❌ 夸克 Cookie 验证失败：{auth_result}"]
    
    logs.append(f"[{movie_name}] ✅ 夸克鉴权成功 (用户: {auth_result})")

    candidates = find_quark_links_for_movie(movie_name, channels)
    if not candidates:
        logs.append(f"[{movie_name}] ❌ 遍历所有预设频道，未检索到相关夸克链接。")
        return logs

    logs.append(f"[{movie_name}] 🔍 共找到 {len(candidates)} 个候选链接，开始逐一校验品质与视频有效性...")

    for ch_name, pwd_id in candidates:
        stoken, token_err = engine.get_share_token(pwd_id)
        if not stoken:
            logs.append(f"[{movie_name}] ⚠️ 频道 [{ch_name}] 链接 ({pwd_id}) token 获取失败: {token_err}，尝试下一个...")
            continue

        fids, fid_tokens, is_single_folder, detail_err = engine.get_share_detail_and_validate(pwd_id, stoken)
        if not fids:
            logs.append(f"[{movie_name}] ⚠️ 频道 [{ch_name}] 链接 ({pwd_id}) 校验拒绝: {detail_err}，尝试下一个...")
            continue

        final_target_fid = target_folder_id
        if not is_single_folder:
            new_fid, mkdir_err = engine.mkdir(movie_name, target_folder_id)
            if new_fid:
                final_target_fid = new_fid
                logs.append(f"[{movie_name}] 📁 检测到多项/散落文件，已自动在云盘创建同名归档文件夹 [{movie_name}]")
            else:
                logs.append(f"[{movie_name}] ⚠️ 新建同名文件夹失败 ({mkdir_err})，将保存至根目录")

        logs.append(f"[{movie_name}] 🎯 频道 [{ch_name}] 命中优质资源！包含 {len(fids)} 个有效项，开始转存...")

        success, msg = engine.save_share_files(pwd_id, stoken, fids, fid_tokens, final_target_fid)
        if success:
            logs.append(f"[{movie_name}] 🎉 成功转存至目标目录 ID: [{final_target_fid}]！")
            return logs
        else:
            logs.append(f"[{movie_name}] ⚠️️ 频道 [{ch_name}] 转存执行失败 ({msg})，尝试下一个...")

    logs.append(f"[{movie_name}] ❌ 尝试完所有候选链接，均未找到含视频的有效影视资源。")
    return logs
