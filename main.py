import os
import json
import datetime
import requests
from flask import Flask, render_template, request, jsonify, Response, session, redirect
from werkzeug.security import generate_password_hash, check_password_hash
from concurrent.futures import ThreadPoolExecutor

from quark_engine import QuarkEngine
from subscription_manager import SubscriptionManager
from search_service import SearchService
from utils import load_channels, save_channels, DOUBAN_HEADERS

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'moviesync_secret_key_2026_secure')

AUTH_FILE = 'auth.json'
CONFIG_FILE = 'config.json'
SYSTEM_LOGS = []

def log_system(msg):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{now}] {msg}"
    SYSTEM_LOGS.append(log_line)
    if len(SYSTEM_LOGS) > 300:
        SYSTEM_LOGS.pop(0)

log_system("MovieSync 服务启动成功")

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

def load_full_config():
    default_config = {
        "quark_cookie": "",
        "default_fid": "0",
        "openlist_url": "https://openlist.88888807.xyz:8807/",
        "category_fids": {
            "电影": "3ef79d1b370a4b27bd334b7bbba7e6e1",
            "电视剧": "fe24e17d8d254997b21710c73b22b6e7",
            "综艺": "6999ba53a9384525881f785976bd09f1",
            "动漫": "55a44b99fac641679e1ebf55dcb38be9"
        },
        "channels": load_channels()
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                default_config.update(saved)
        except Exception as e:
            log_system(f"读取 config.json 失败: {e}")
    return default_config

def save_full_config(config_data):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        if 'channels' in config_data:
            save_channels(config_data['channels'])
        log_system("配置已成功持久化至 config.json")
        return True
    except Exception as e:
        log_system(f"保存 config.json 失败: {e}")
        return False

sub_manager = SubscriptionManager(get_cookie_func=lambda: load_full_config().get('quark_cookie', ''))
sub_manager.start_scheduler()

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
    if request.path not in ['/login', '/api/login'] and not session.get('logged_in'):
        if request.path.startswith('/api/'):
            return jsonify({'success': False, 'message': '未登录', 'need_login': True}), 401
        return redirect('/login')

@app.route('/setup')
def setup_page(): return render_template('login.html', is_setup=True)

@app.route('/api/setup', methods=['POST'])
def api_setup():
    auth_data = load_auth()
    if auth_data and auth_data.get('initialized'):
        return jsonify({'success': False, 'message': '系统已完成初始化'})
    data = request.json or {}
    username, password = data.get('username', '').strip(), data.get('password', '').strip()
    if not username or not password:
        return jsonify({'success': False, 'message': '账号与密码不能为空'})
    save_auth({"initialized": True, "username": username, "password_hash": generate_password_hash(password)})
    session['logged_in'], session['username'] = True, username
    return jsonify({'success': True, 'message': '管理员账号创建成功！'})

@app.route('/login')
def login_page(): return render_template('login.html', is_setup=False)

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json or {}
    username, password = data.get('username', '').strip(), data.get('password', '').strip()
    auth_data = load_auth()
    if auth_data and username == auth_data.get('username') and check_password_hash(auth_data.get('password_hash'), password):
        session['logged_in'], session['username'] = True, username
        return jsonify({'success': True, 'message': '登录成功'})
    return jsonify({'success': False, 'message': '用户名或密码错误'})

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/')
def index(): return render_template('index.html')

@app.route('/admin')
def admin(): return render_template('admin.html')

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    if request.method == 'GET':
        return jsonify({'success': True, 'config': load_full_config()})
    data = request.json or {}
    if save_full_config(data):
        return jsonify({'success': True, 'message': '配置已全部保存'})
    return jsonify({'success': False, 'message': '保存失败'})

@app.route('/api/admin/logs', methods=['GET'])
def get_admin_logs(): return jsonify({'success': True, 'logs': SYSTEM_LOGS})

@app.route('/api/check-cookie', methods=['POST'])
def check_cookie():
    try:
        data = request.json or {}
        cookie = data.get('cookie', '').strip() or load_full_config().get('quark_cookie', '')
        engine = QuarkEngine(cookie)
        valid = engine.check_cookie_valid()
        return jsonify({'valid': valid, 'message': 'Cookie 有效' if valid else 'Cookie 已失效'})
    except Exception as e:
        return jsonify({'valid': False, 'message': str(e)})

@app.route('/api/check-channels', methods=['GET'])
def check_channels_health():
    try:
        config = load_full_config()
        channels = config.get('channels', [])
        if not channels:
            return jsonify({'success': True, 'total': 0, 'valid_count': 0})

        def test_channel(ch):
            ch_id = ch.get('id', '').strip() if isinstance(ch, dict) else str(ch).strip()
            if not ch_id: return False
            try:
                resp = requests.get(f"https://t.me/s/{ch_id}", headers={'User-Agent': 'Mozilla/5.0'}, timeout=4)
                return resp.status_code == 200 and "tgme_channel_info" in resp.text
            except Exception:
                return False

        with ThreadPoolExecutor(max_workers=5) as executor:
            valid_count = sum(1 for v in executor.map(test_channel, channels) if v)

        return jsonify({'success': True, 'total': len(channels), 'valid_count': valid_count})
    except Exception as e:
        return jsonify({'success': False, 'total': 0, 'valid_count': 0, 'error': str(e)})

@app.route('/api/get-movies', methods=['GET'])
def get_movies():
    main_tag = request.args.get('tag', '电影')
    sort_type = request.args.get('sort', 'U')
    genre = request.args.get('genre', '')
    url = "https://m.douban.com/rexxar/api/v2/tv/recommend" if main_tag != '电影' else "https://m.douban.com/rexxar/api/v2/subject/recent_hot/movie"
    headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://movie.douban.com/"}
    try:
        if main_tag == '电影':
            params = {"start": "0", "limit": "100", "category": "最新" if sort_type in ['T', 'R'] else "热门", "type": "全部"}
        else:
            cat_map = {"动漫": {"类型": "动画", "形式": "电视剧"}, "综艺": {"类型": "", "形式": "综艺"}, "电视剧": {"类型": "", "形式": "电视剧"}}
            params = {"refresh": "0", "start": "0", "count": "100", "selected_categories": json.dumps(cat_map.get(main_tag, {"类型": "", "形式": "电视剧"}), ensure_ascii=False), "tags": genre if genre and genre != '全部' else main_tag, "sort": "R" if sort_type in ['T', 'R'] else "U"}
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        if resp.status_code == 200:
            items = resp.json().get('subjects', []) or resp.json().get('items', [])
            movies = [{'title': item.get('title'), 'cover': (item.get('pic') or {}).get('normal', item.get('cover', '')), 'rate': str((item.get('rating') or {}).get('value', '暂无')), 'url': f"https://movie.douban.com/subject/{item.get('id') or (item.get('target') or {}).get('id')}/"} for item in items if item.get('title')]
            return jsonify({'success': True, 'movies': movies})
    except Exception as e:
        log_system(f"获取豆瓣失败: {e}")
    return jsonify({'success': False, 'movies': []})

@app.route('/api/search-douban', methods=['GET'])
def search_douban():
    query = request.args.get('q', '').strip()
    if not query: return jsonify({'success': False, 'movies': []})
    try:
        resp = requests.get(f"https://movie.douban.com/j/subject_suggest?q={requests.utils.quote(query)}", headers=DOUBAN_HEADERS, timeout=8)
        if resp.status_code == 200:
            movies = [{'title': i.get('title'), 'cover': i.get('img'), 'rate': i.get('year', '搜索'), 'url': f"https://movie.douban.com/subject/{i.get('id')}/"} for i in resp.json()]
            return jsonify({'success': True, 'movies': movies})
    except Exception:
        pass
    return jsonify({'success': False, 'movies': []})

@app.route('/api/channels', methods=['GET', 'POST'])
def handle_channels():
    config = load_full_config()
    if request.method == 'POST':
        config['channels'] = request.json.get('channels', [])
        save_full_config(config)
        return jsonify({'success': True})
    return jsonify({'success': True, 'channels': config.get('channels', [])})

@app.route('/api/search-candidates', methods=['POST'])
def api_search_candidates():
    data = request.json or {}
    movies = data.get('movies', [])
    config = load_full_config()
    cookie = data.get('cookie', '').strip() or config.get('quark_cookie', '')
    
    if not movies: 
        return jsonify({'success': False, 'message': '未选择影片'})
    if not cookie: 
        return jsonify({'success': False, 'message': '未配置夸克 Cookie'})

    service = SearchService(cookie)
    channels = config.get('channels', [])
    
    candidates_map = {}
    for movie in movies:
        title = movie.get('title', str(movie)) if isinstance(movie, dict) else str(movie)
        log_system(f"正在搜刮《{title}》的候选资源...")
        candidates = service.search_movie_candidates(movie, channels)
        candidates_map[title] = candidates

    return jsonify({'success': True, 'candidates_map': candidates_map})

@app.route('/api/transfer-selected', methods=['POST'])
def api_transfer_selected():
    data = request.json or {}
    movie = data.get('movie')
    candidate = data.get('candidate')
    config = load_full_config()
    cookie = data.get('cookie', '').strip() or config.get('quark_cookie', '')
    
    if not movie or not candidate:
        return jsonify({'success': False, 'message': '参数不完整'})
    if not cookie:
        return jsonify({'success': False, 'message': '未配置夸克 Cookie'})

    service = SearchService(cookie)
    default_fid = config.get('default_fid', '0')
    category_fids = config.get('category_fids', {})

    title = movie.get('title', '未知影片') if isinstance(movie, dict) else str(movie)
    log_system(f"用户已确认选择，开始转存《{title}》...")

    success, msg = service.transfer_selected_resource(
        movie=movie,
        candidate=candidate,
        target_fid=default_fid,
        category_fids=category_fids
    )
    
    log_system(msg)
    if success:
        return jsonify({'success': True, 'message': msg})
    else:
        return jsonify({'success': False, 'message': msg})

@app.route('/api/subscriptions', methods=['GET', 'POST', 'DELETE'])
def handle_subscriptions():
    if request.method == 'GET':
        return jsonify({'success': True, 'subscriptions': sub_manager.get_subscriptions()})
    if request.method == 'POST':
        data = request.json or {}
        sub = sub_manager.add_subscription(
            title=data.get('title'),
            pwd_id=data.get('pwd_id'),
            target_fid=data.get('target_fid') or load_full_config().get('default_fid', '0'),
            interval_hours=int(data.get('interval_hours', 6)),
            channel=data.get('channel', ''),
            stoken=data.get('stoken', ''),
            files=data.get('files', [])
        )
        log_system(f"成功添加智能追剧任务: 《{data.get('title')}》 (存储FID: {sub.get('target_fid')}, 频道: {data.get('channel')})")
        return jsonify({'success': True, 'subscription': sub, 'message': '智能追剧任务添加成功！'})
    
    sub_id = request.args.get('id') or (request.json or {}).get('id')
    if sub_id:
        sub_manager.delete_subscription(sub_id)
        log_system(f"已删除订阅任务 ID: {sub_id}")
    return jsonify({'success': True, 'message': '已删除订阅'})

@app.route('/api/subscriptions/run-now', methods=['POST'])
def api_run_subscription_now():
    data = request.json or {}
    sub_id = data.get('id')
    if not sub_id:
        return jsonify({'success': False, 'message': '未提供订阅 ID'})
    
    success, msg = sub_manager.check_subscription_now(sub_id)
    log_system(f"手动触发追剧: {msg}")
    return jsonify({'success': success, 'message': msg})

@app.route('/api/proxy-img')
def proxy_img():
    url = request.args.get('url')
    if not url: return Response("Missing url", status=400)
    try:
        resp = requests.get(url, headers=DOUBAN_HEADERS, timeout=8)
        return Response(resp.content, mimetype=resp.headers.get('content-type', 'image/jpeg'))
    except Exception:
        return Response("", status=404)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
