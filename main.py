import os
import json
import requests
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
    # 默认账户: admin / admin123  重置密码 Token: moviesync2026
    default_auth = {
        "username": "admin",
        "password_hash": generate_password_hash("admin123"),
        "reset_token": "moviesync2026"
    }
    save_auth(default_auth)
    return default_auth

def save_auth(data):
    with open(AUTH_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# 初始化追剧订阅管理器
sub_manager = SubscriptionManager(get_cookie_func=lambda: app.config.get('QUARK_COOKIE', ''))
sub_manager.start_scheduler()

# 🎯 登录全局拦截器 (未登录访问任何页面自动重定向到 /login)
@app.before_request
def require_login():
    allowed_paths = ['/login', '/api/login', '/api/reset-password']
    if request.path.startswith('/static') or request.path in allowed_paths:
        return
    if not session.get('logged_in'):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'message': '未登录', 'need_login': True}), 401
        return redirect('/login')

@app.route('/login')
def login_page():
    if session.get('logged_in'):
        return redirect('/')
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    auth_data = load_auth()
    if username == auth_data.get('username') and check_password_hash(auth_data.get('password_hash'), password):
        session['logged_in'] = True
        session['username'] = username
        return jsonify({'success': True, 'message': '登录成功'})
    return jsonify({'success': False, 'message': '用户名或密码错误'})

@app.route('/api/reset-password', methods=['POST'])
def api_reset_password():
    data = request.json or {}
    token = data.get('token', '').strip()
    new_password = data.get('new_password', '').strip()

    if not token or not new_password:
        return jsonify({'success': False, 'message': '请填写完整凭证与新密码'})

    auth_data = load_auth()
    if token != auth_data.get('reset_token'):
        return jsonify({'success': False, 'message': '重置凭证 Token 错误'})

    auth_data['password_hash'] = generate_password_hash(new_password)
    save_auth(auth_data)
    return jsonify({'success': True, 'message': '密码重置成功，请重新登录'})

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

# ==================== 影视与转存 API ====================

@app.route('/api/get-movies', methods=['GET'])
def get_movies():
    main_tag = request.args.get('tag', '电影')
    sort_type = request.args.get('sort', 'U')
    genre = request.args.get('genre', '')
    country = request.args.get('country', '')
    year_range = request.args.get('year', '')

    if main_tag == '动漫':
        main_tag = '动画'

    url = "https://movie.douban.com/j/new_search_subjects"
    params = {
        "sort": sort_type,
        "range": "0,10",
        "tags": main_tag,
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
        content_type = resp.headers.get('Content-Type', '')
        if 'html' in content_type.lower():
            return jsonify({'success': False, 'movies': [], 'message': '豆瓣触发风控拦截'})

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
    files, stoken, err = engine.get_share_files(pwd_id)
    if not files:
        return jsonify({'success': False, 'message': f'解析失败: {err}'})

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

    if not selected_fids or not cookie:
        return jsonify({'success': False, 'message': '未选择文件或缺失 Cookie'})

    engine = QuarkEngine(cookie)
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
        return jsonify({'success': False, 'message': f'未在所设频道中找到 [{title}] 的夸克链接'})
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
    cookie = data.get('cookie', '')
    folder_id = data.get('folderId', '0')

    if not movies or not cookie:
        return Response("❌ 参数不完整\n", mimetype='text/plain; charset=utf-8')

    service = SearchService(cookie)
    channels = load_channels()

    def generate_logs():
        for line in service.batch_search_and_transfer_stream(movies, channels, target_fid=folder_id):
            yield line + "\n"

    return Response(stream_with_context(generate_logs()), mimetype='text/plain; charset=utf-8')

@app.route('/api/proxy-img')
def proxy_img():
    img_url = request.args.get('url')
    if not img_url:
        return Response("Missing url", status=400)
    try:
        resp = requests.get(img_url, headers=DOUBAN_HEADERS, timeout=8)
        return Response(resp.content, mimetype=resp.headers.get('content-type', 'image/jpeg'))
    except Exception:
        return Response("", status=404)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
