import os
import json
import datetime
import requests
import re
from flask import Flask, render_template, request, jsonify, Response, stream_with_context, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from concurrent.futures import ThreadPoolExecutor

from quark_engine import QuarkEngine, clean_tv_filename
from subscription_manager import SubscriptionManager
from search_service import SearchService
from utils import load_channels, save_channels, DOUBAN_HEADERS

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'moviesync_secret_key_2026_secure')

AUTH_FILE = 'auth.json'

def load_auth():
    if os.path.exists(AUTH_FILE):
        try:
            with open(AUTH_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return None

def save_auth(data):
    with open(AUTH_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

sub_manager = SubscriptionManager(get_cookie_func=lambda: app.config.get('QUARK_COOKIE', ''))
sub_manager.start_scheduler()

# 🎯 全局登录与初始化拦截器
@app.before_request
def require_login():
    if request.path.startswith('/static'):
        return

    auth_data = load_auth()

    if not auth_data or not auth_data.get('initialized'):
        if request.path not in ['/setup', '/api/setup']:
            return redirect('/setup')
        return

    if request.path in ['/setup', '/api/setup']:
        return redirect('/login')

    allowed_paths = ['/login', '/api/login']
    if request.path not in allowed_paths and not session.get('logged_in'):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'message': '未登录', 'need_login': True}), 401
        return redirect('/login')

@app.route('/setup')
def setup_page():
    return render_template('login.html', is_setup=True)

@app.route('/api/setup', methods=['POST'])
def api_setup():
    auth_data = load_auth()
    if auth_data and auth_data.get('initialized'):
        return jsonify({'success': False, 'message': '系统已完成初始化'})

    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'success': False, 'message': '账号与密码不能为空'})

    new_auth = {
        "initialized": True,
        "username": username,
        "password_hash": generate_password_hash(password)
    }
    save_auth(new_auth)

    session['logged_in'] = True
    session['username'] = username
    return jsonify({'success': True, 'message': '管理员账号创建成功！'})

@app.route('/login')
def login_page():
    if session.get('logged_in'):
        return redirect('/')
    return render_template('login.html', is_setup=False)

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    auth_data = load_auth()
    if auth_data and username == auth_data.get('username') and check_password_hash(auth_data.get('password_hash'), password):
        session['logged_in'] = True
        session['username'] = username
        return jsonify({'success': True, 'message': '登录成功'})
    return jsonify({'success': False, 'message': '用户名或密码错误'})

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin():
    return render_template('admin.html')

# ==================== 🎯 抓包 API 数据解析与逻辑封装 ====================

REXXAR_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://movie.douban.com/",
    "Accept": "application/json, text/plain, */*"
}

def parse_rexxar_items(items):
    """通用提取 Rexxar 返回的影视条目"""
    movies = []
    for item in items:
        title = item.get('title', '')
        if not title:
            continue
        
        # 封面获取
        cover = ''
        if isinstance(item.get('pic'), dict):
            cover = item['pic'].get('normal') or item['pic'].get('large') or ''
        elif item.get('cover'):
            cover = item.get('cover')
        elif item.get('cover_url'):
            cover = item.get('cover_url')

        # 评分获取
        rate = '暂无'
        if isinstance(item.get('rating'), dict):
            val = item['rating'].get('value')
            if val and float(val) > 0:
                rate = str(val)
        elif item.get('rate'):
            rate = str(item.get('rate'))

        # ID及详情页URL
        target_id = item.get('id')
        if not target_id and isinstance(item.get('target'), dict):
            target_id = item['target'].get('id')
        if not target_id and 'uri' in item:
            m_id = re.search(r'/(\d+)', str(item.get('uri')))
            if m_id:
                target_id = m_id.group(1)

        url = f"https://movie.douban.com/subject/{target_id}/" if target_id else '#'
        
        movies.append({
            'title': title,
            'cover': cover,
            'rate': rate,
            'url': url
        })
    return movies

def fetch_movie_recent_hot(category='热门'):
    """针对【电影】的抓包 API: subject/recent_hot/movie"""
    url = "https://m.douban.com/rexxar/api/v2/subject/recent_hot/movie"
    params = {
        "start": "0",
        "limit": "100",
        "category": category, # '热门' 或 '最新'
        "type": "全部"
    }
    try:
        resp = requests.get(url, headers=REXXAR_HEADERS, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('subjects', []) or data.get('items', [])
            return parse_rexxar_items(items)
    except Exception as e:
        print(f"请求电影 Rexxar 接口异常: {e}")
    return None

def fetch_tv_recommend(main_tag, sort_type='U', genre=''):
    """针对【电视剧/综艺/动画】的抓包 API: tv/recommend"""
    url = "https://m.douban.com/rexxar/api/v2/tv/recommend"
    
    if main_tag in ['动漫', '动画']:
        sel_cat = {"类型": "动画", "形式": "电视剧"}
        tag_str = genre if genre else "动画"
    elif main_tag == '综艺':
        sel_cat = {"类型": "", "形式": "综艺"}
        tag_str = genre if genre else "综艺"
    else: # 电视剧
        sel_cat = {"类型": "", "形式": "电视剧"}
        tag_str = genre if genre else "电视剧"

    # 🎯 核心映射：抓包证实 sort=R 为最新，sort=U 为热门，sort=S 为高分
    real_sort = 'U'
    if sort_type in ['T', 'R']:
        real_sort = 'R'
    elif sort_type == 'S':
        real_sort = 'S'

    params = {
        "refresh": "0",
        "start": "0",
        "count": "100",
        "selected_categories": json.dumps(sel_cat, ensure_ascii=False),
        "uncollect": "false",
        "score_range": "0,10",
        "tags": tag_str,
        "sort": real_sort
    }
    try:
        resp = requests.get(url, headers=REXXAR_HEADERS, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('items', []) or data.get('subjects', [])
            return parse_rexxar_items(items)
    except Exception as e:
        print(f"请求 TV Rexxar 接口异常: {e}")
    return None

@app.route('/api/get-movies', methods=['GET'])
def get_movies():
    main_tag = request.args.get('tag', '电影')
    sort_type = request.args.get('sort', 'U')  # U: 热门, T/R: 最新, S: 高分
    genre = request.args.get('genre', '')
    country = request.args.get('country', '')
    year_range = request.args.get('year', '')

    # 1. 如果是大分类“电影”
    if main_tag == '电影':
        category = '最新' if sort_type in ['T', 'R'] else '热门'
        movies = fetch_movie_recent_hot(category=category)
        if movies:
            return jsonify({'success': True, 'movies': movies})

    # 2. 如果是大分类“电视剧”、“综艺”、“动漫/动画”
    if main_tag in ['电视剧', '综艺', '动漫', '动画']:
        movies = fetch_tv_recommend(main_tag, sort_type=sort_type, genre=genre)
        if movies:
            return jsonify({'success': True, 'movies': movies})

    # 3. 降级备用（常规 Web API）
    search_tag = '动画' if main_tag in ['动漫', '动画'] else main_tag
    url = "https://movie.douban.com/j/new_search_subjects"
    params = {
        "sort": sort_type,
        "range": "0,10",
        "tags": search_tag,
        "start": 0,
        "limit": 100
    }
    if genre:
        params["genres"] = genre
    if country:
        params["countries"] = country
    if year_range:
        params["year_range"] = year_range

    try:
        resp = requests.get(url, headers=DOUBAN_HEADERS, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            raw_list = data.get('data', [])
            movies = [{
                'title': item.get('title'),
                'cover': item.get('cover'),
                'rate': item.get('rate') if item.get('rate') else '暂无',
                'url': item.get('url', f"https://movie.douban.com/subject/{item.get('id')}/")
            } for item in raw_list]
            return jsonify({'success': True, 'movies': movies})
        return jsonify({'success': False, 'movies': [], 'message': f'豆瓣响应异常: HTTP {resp.status_code}'})
    except Exception as e:
        return jsonify({'success': False, 'movies': [], 'message': f'请求异常: {str(e)}'})

@app.route('/api/search-douban', methods=['GET'])
def search_douban():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'success': False, 'movies': []})
    url = f"https://movie.douban.com/j/subject_suggest?q={requests.utils.quote(query)}"
    try:
        resp = requests.get(url, headers=DOUBAN_HEADERS, timeout=8)
        content_type = resp.headers.get('Content-Type', '')
        if 'html' in content_type.lower():
            return jsonify({'success': False, 'movies': [], 'message': '搜索触发风控'})

        if resp.status_code == 200:
            data = resp.json()
            movies = [{
                'title': item.get('title'),
                'cover': item.get('img'),
                'rate': item.get('year', '搜索'),
                'url': f"https://movie.douban.com/subject/{item.get('id')}/"
            } for item in data]
            return jsonify({'success': True, 'movies': movies})
        return jsonify({'success': False, 'movies': []})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'movies': []})

@app.route('/api/check-cookie', methods=['POST'])
def check_cookie():
    try:
        data = request.json or {}
        cookie = data.get('cookie', '')
        if not cookie:
            return jsonify({'valid': False, 'message': '未配置 Cookie'})
        engine = QuarkEngine(cookie)
        valid = engine.check_cookie_valid()
        if valid:
            app.config['QUARK_COOKIE'] = cookie
        return jsonify({'valid': valid, 'message': 'Cookie 有效' if valid else 'Cookie 已失效'})
    except Exception as e:
        return jsonify({'valid': False, 'message': f'校验出错: {str(e)}'})

@app.route('/api/check-channels', methods=['GET'])
def check_channels_health():
    try:
        channels = load_channels()
        if not channels:
            return jsonify({'success': True, 'total': 0, 'valid_count': 0})

        def test_channel(ch):
            ch_id = ch.get('id', '').strip()
            if not ch_id:
                return False
            url = f"https://t.me/s/{ch_id}"
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            try:
                resp = requests.head(url, headers=headers, timeout=3.0)
                return resp.status_code == 200
            except Exception:
                return False

        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(test_channel, channels))

        valid_count = sum(1 for is_valid in results if is_valid)
        return jsonify({
            'success': True,
            'total': len(channels),
            'valid_count': valid_count
        })
    except Exception as e:
        return jsonify({'success': False, 'total': 0, 'valid_count': 0, 'error': str(e)})

@app.route('/api/channels', methods=['GET', 'POST'])
def handle_channels():
    if request.method == 'POST':
        channels = request.json.get('channels', [])
        save_channels(channels)
        return jsonify({'success': True})
    return jsonify({'success': True, 'channels': load_channels()})

@app.route('/api/parse-share-detail', methods=['POST'])
def parse_share_detail():
    data = request.json or {}
    pwd_id = data.get('pwd_id', '').strip()
    title = data.get('title', '未命名剧集')
    cookie = data.get('cookie', '')

    if not pwd_id or not cookie:
        return jsonify({'success': False, 'message': '参数缺失'})

    engine = QuarkEngine(cookie)
    files, stoken, err = engine.get_share_files(pwd_id, only_video=True)
    if not files:
        return jsonify({'success': False, 'message': f'未包含有效视频文件: {err}'})

    parsed_files = []
    for f in files:
        raw_name = f.get('file_name', '')
        size_mb = round(f.get('size', 0) / (1024 * 1024), 1)
        size_str = f"{size_mb} MB" if size_mb < 1024 else f"{round(size_mb/1024, 2)} GB"
        
        ep_num, cleaned_name = clean_tv_filename(raw_name, title)
        
        parsed_files.append({
            'fid': f.get('fid'),
            'raw_name': raw_name,
            'cleaned_name': cleaned_name,
            'ep_num': ep_num,
            'size_str': size_str,
            'is_video': ep_num is not None
        })

    return jsonify({
        'success': True,
        'pwd_id': pwd_id,
        'stoken': stoken,
        'files': parsed_files
    })

@app.route('/api/save-selected-files', methods=['POST'])
def save_selected_files():
    data = request.json or {}
    pwd_id = data.get('pwd_id')
    stoken = data.get('stoken')
    selected_fids = data.get('fids', [])
    target_fid = data.get('target_fid', '0')
    cookie = data.get('cookie', '')
    title = data.get('title', '')

    if not selected_fids or not cookie:
        return jsonify({'success': False, 'message': '未选择文件或缺失 Cookie'})

    engine = QuarkEngine(cookie)
    
    if title:
        target_fid = engine.get_or_create_subfolder(title, target_fid)

    files_to_save = [{'fid': fid} for fid in selected_fids]
    
    ok, msg = engine.save_files(pwd_id, files_to_save, stoken, target_fid)
    return jsonify({'success': ok, 'message': msg})

@app.route('/api/search-link-for-sub', methods=['POST'])
def search_link_for_sub():
    try:
        data = request.json or {}
        title = data.get('title', '').strip()
        cookie = data.get('cookie', '')
        if not title:
            return jsonify({'success': False, 'message': '未传入剧集名称'})

        channels = load_channels()
        if not channels:
            return jsonify({'success': False, 'message': '未配置 TG 检索频道'})

        service = SearchService(cookie)
        pwd_id = service.search_single_movie_pwd_id(title, channels)
        
        if pwd_id:
            return jsonify({'success': True, 'pwd_id': pwd_id})
        return jsonify({'success': False, 'message': f'未在频道中找到含有视频的 [{title}] 链接'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'后台检索异常: {str(e)}'})

@app.route('/api/subscriptions', methods=['GET', 'POST', 'DELETE'])
def handle_subscriptions():
    if request.method == 'GET':
        return jsonify({'success': True, 'subscriptions': sub_manager.get_subscriptions()})

    if request.method == 'POST':
        data = request.json or {}
        cookie = data.get('cookie', '')
        if cookie:
            app.config['QUARK_COOKIE'] = cookie
        
        new_sub = sub_manager.add_subscription(
            title=data.get('title'),
            pwd_id=data.get('pwd_id'),
            target_fid=data.get('target_fid', '0'),
            interval_hours=data.get('interval_hours', 6),
            start_ep=data.get('start_ep', 0)
        )
        return jsonify({'success': True, 'subscription': new_sub})

    if request.method == 'DELETE':
        sub_id = request.args.get('id')
        sub_manager.delete_subscription(sub_id)
        return jsonify({'success': True})

@app.route('/api/subscriptions/run-now', methods=['POST'])
def run_sub_now():
    data = request.json or {}
    sub_id = data.get('id')
    cookie = data.get('cookie', '')
    if cookie:
        app.config['QUARK_COOKIE'] = cookie
        
    ok, msg = sub_manager.check_subscription_now(sub_id)
    return jsonify({'success': ok, 'message': msg})

@app.route('/api/transfer', methods=['POST'])
def transfer():
    data = request.json or {}
    movies = data.get('movies', [])
    # 🎯 关键兼容：如果请求体未带 cookie，自动获取后端全局配置的 QUARK_COOKIE
    cookie = data.get('cookie', '').strip() or app.config.get('QUARK_COOKIE', '')
    folder_id = data.get('folderId', '0')

    if not movies:
        return Response("❌ 未选择任何需要转存的影片\n", mimetype='text/plain; charset=utf-8')
        
    if not cookie:
        return Response("❌ 未配置夸克网盘 Cookie！请先点击右上角 [设置] 保存 Cookie。\n", mimetype='text/plain; charset=utf-8')

    service = SearchService(cookie)
    channels = load_channels()

    def generate_logs():
        for line in service.batch_search_and_transfer_stream(movies, channels, target_fid=folder_id):
            yield line

    return Response(stream_with_context(generate_logs()), mimetype='text/plain; charset=utf-8')

@app.route('/api/proxy-img')
def proxy_img():
    img_url = request.args.get('url')
    if not img_url:
        return Response("Missing url", status=400)
    try:
        resp = requests.get(img_url, headers=REXXAR_HEADERS, timeout=8)
        return Response(resp.content, mimetype=resp.headers.get('content-type', 'image/jpeg'))
    except Exception:
        return Response("", status=404)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
