import os
import json
import requests
import re
from flask import Flask, render_template, request, jsonify, Response, stream_with_context, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

from quark_engine import QuarkEngine
from search_service import SearchService
from utils import load_channels, save_channels, DOUBAN_HEADERS

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'moviesync_secret_key_2026_secure')

# 预设专属分类 FID 映射配置
CATEGORY_FIDS = {
    "电影": "3ef79d1b370a4b27bd334b7bbba7e6e1",
    "电视剧": "fe24e17d8d254997b21710c73b22b6e7",
    "综艺": "6999ba53a9384525881f785976bd09f1",
    "动漫": "55a44b99fac641679e1ebf55dcb38be9"
}

@app.before_request
def require_login():
    if request.path.startswith('/static'):
        return
    allowed_paths = ['/login', '/api/login', '/setup', '/api/setup']
    if request.path not in allowed_paths and not session.get('logged_in'):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'message': '未登录'}), 401
        return redirect('/login')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/api/get-movies', methods=['GET'])
def get_movies():
    main_tag = request.args.get('tag', '电影')
    sort_type = request.args.get('sort', 'U')
    genre = request.args.get('genre', '')
    
    url = "https://m.douban.com/rexxar/api/v2/tv/recommend" if main_tag != '电影' else "https://m.douban.com/rexxar/api/v2/subject/recent_hot/movie"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://movie.douban.com/"
    }
    
    try:
        if main_tag == '电影':
            params = {"start": "0", "limit": "100", "category": "最新" if sort_type in ['T', 'R'] else "热门", "type": "全部"}
        else:
            cat_map = {"动漫": {"类型": "动画", "形式": "电视剧"}, "综艺": {"类型": "", "形式": "综艺"}, "电视剧": {"类型": "", "形式": "电视剧"}}
            sel_cat = cat_map.get(main_tag, {"类型": "", "形式": "电视剧"})
            params = {
                "refresh": "0", "start": "0", "count": "100",
                "selected_categories": json.dumps(sel_cat, ensure_ascii=False),
                "tags": genre if genre and genre != '全部' else main_tag,
                "sort": "R" if sort_type in ['T', 'R'] else "U"
            }
            
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('subjects', []) or data.get('items', [])
            movies = []
            for item in items:
                title = item.get('title', '')
                if not title: continue
                cover = item.get('pic', {}).get('normal') if isinstance(item.get('pic'), dict) else item.get('cover', '')
                rate = str(item.get('rating', {}).get('value', '暂无')) if isinstance(item.get('rating'), dict) else '暂无'
                target_id = item.get('id') or (item.get('target', {}).get('id') if isinstance(item.get('target'), dict) else '')
                movies.append({'title': title, 'cover': cover, 'rate': rate, 'url': f"https://movie.douban.com/subject/{target_id}/" if target_id else '#'})
            return jsonify({'success': True, 'movies': movies})
    except Exception as e:
        print(f"请求异常: {e}")
    return jsonify({'success': False, 'movies': []})

@app.route('/api/channels', methods=['GET', 'POST'])
def handle_channels():
    if request.method == 'POST':
        channels = request.json.get('channels', [])
        save_channels(channels)
        return jsonify({'success': True})
    return jsonify({'success': True, 'channels': load_channels()})

# 🎯 核心修复：转存逻辑映射专属 FID 与新建文件夹
@app.route('/api/transfer', methods=['POST'])
def transfer():
    data = request.json or {}
    movies = data.get('movies', [])
    cookie = data.get('cookie', '').strip() or app.config.get('QUARK_COOKIE', '')

    if not movies:
        return Response("[系统] ❌ 未选择任何影片\n", mimetype='text/plain; charset=utf-8')
    if not cookie:
        return Response("[系统] ❌ 未配置夸克 Cookie！请先在后台保存夸克 Cookie。\n", mimetype='text/plain; charset=utf-8')

    service = SearchService(cookie)
    channels = load_channels()

    def generate_logs():
        yield f"[系统] 🚀 开始处理批量转存，共 {len(movies)} 个目标...\n"
        for idx, movie in enumerate(movies, 1):
            title = movie.get('title', '').strip()
            tag = movie.get('tag', '电影')
            
            # 获取对应的分类专属 FID
            target_parent_fid = CATEGORY_FIDS.get(tag, '0')
            
            yield f"\n[系统] 🔍 [{idx}/{len(movies)}] 正在检索：《{title}》（分类: {tag}）...\n"

            pwd_id, ch_name = service.search_single_movie(title, channels)
            if not pwd_id:
                yield f"[系统] ❌ 未能在已配置频道中找到《{title}》的有效资源\n"
                continue

            yield f"[系统] 📢 [来源频道: {ch_name}] 精确命中《{title}》 | 夸克代码: {pwd_id}\n"
            yield f"[系统] 🔎 正在穿透解析资源内容...\n"

            files, stoken, err = service.engine.get_share_files(pwd_id, only_video=True)
            if not files:
                yield f"[系统] ⚠️ 资源解析失败: {err}\n"
                continue

            # 🎯 专属目录新建文件夹
            yield f"[系统] 📁 正在专属存储目录下新建/定位文件夹：《{title}》...\n"
            movie_folder_fid = service.engine.get_or_create_subfolder(title, target_parent_fid)

            files_to_save = [{'fid': f['fid']} for f in files]
            ok, msg = service.engine.save_files(pwd_id, files_to_save, stoken, movie_folder_fid)

            if ok:
                yield f"[系统] ✅ 《{title}》已成功转存至专属文件夹《{title}》中！(共 {len(files)} 个视频文件)\n"
            else:
                yield f"[系统] ❌ 转存失败: {msg}\n"

    return Response(stream_with_context(generate_logs()), mimetype='text/plain; charset=utf-8')

@app.route('/api/proxy-img')
def proxy_img():
    img_url = request.args.get('url')
    if not img_url: return Response("Missing url", status=400)
    try:
        resp = requests.get(img_url, headers=DOUBAN_HEADERS, timeout=8)
        return Response(resp.content, mimetype=resp.headers.get('content-type', 'image/jpeg'))
    except Exception:
        return Response("", status=404)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
