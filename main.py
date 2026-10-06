import os
import json
import re
import requests
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from quark_engine import QuarkEngine
from search_service import SearchService
from subscription_manager import SubscriptionManager
from utils import load_channels, DOUBAN_HEADERS

app = Flask(__name__)
app.secret_key = 'moviesync-secure-static-secret-key-2026'

CONFIG_FILE = 'config.json'

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_config(config_data):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, ensure_ascii=False, indent=4)

def load_auth():
    if not os.path.exists(CONFIG_FILE):
        return None, None
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('username'), data.get('password_hash')
    except:
        return None, None

def save_auth(username, password_hash):
    data = load_config()
    data['username'] = username
    data['password_hash'] = password_hash
    save_config(data)

# ==================== 鉴权拦截器 ====================
@app.before_request
def require_login():
    username_saved, _ = load_auth()
    allowed_prefixes = ['/login', '/api/setup', '/static']
    if any(request.path.startswith(p) for p in allowed_prefixes):
        return None
        
    if not username_saved and request.endpoint != 'login' and not request.path.startswith('/api/'):
        return redirect(url_for('login'))
        
    if not session.get('logged_in'):
        if request.path.startswith('/api/'):
            return jsonify({"success": False, "message": "未登录或会话已过期，请重新登录"}), 401
        return redirect(url_for('login'))

# ==================== 页面视图路由 ====================
@app.route('/')
def index():
    username_saved, _ = load_auth()
    if not username_saved or not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('index.html')

@app.route('/admin')
def admin():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('admin.html')

@app.route('/openlist')
def openlist():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    if os.path.exists('templates/openlist.html'):
        return render_template('openlist.html')
    return "OpenList 页面未配置"

@app.route('/login', methods=['GET', 'POST'])
def login():
    username_saved, password_hash = load_auth()
    if not username_saved:
        return render_template('login.html', is_setup=True)
    
    if request.method == 'GET':
        if session.get('logged_in'):
            return jsonify({'success': True}), 200
        return render_template('login.html', is_setup=False)

    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')

    if username == username_saved and check_password_hash(password_hash, password):
        session['logged_in'] = True
        return jsonify({'success': True, 'message': '登录成功'})
    return jsonify({'success': False, 'message': '账号或密码错误'}), 401

@app.route('/logout')
def logout():
    session.clear()
    return jsonify({'success': True})

# ==================== API 交互接口 ====================
@app.route('/api/setup', methods=['POST'])
def setup():
    username_saved, _ = load_auth()
    if username_saved:
        return jsonify({'success': False, 'message': '系统已初始化'}), 400
    
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'success': False, 'message': '账号密码不能为空'}), 400

    pwd_hash = generate_password_hash(password)
    save_auth(username, pwd_hash)
    session['logged_in'] = True
    return jsonify({'success': True, 'message': '初始化成功'})

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    if request.method == 'GET':
        config = load_config()
        return jsonify({'success': True, 'config': config})
    
    data = request.get_json() or {}
    config = load_config()
    config.update(data)
    save_config(config)
    return jsonify({'success': True, 'message': '配置保存成功'})

@app.route('/api/get-movies', methods=['GET'])
def get_movies():
    tag = request.args.get('tag', '电影')
    sort = request.args.get('sort', 'U')
    try:
        movies = SearchService.get_douban_movies(tag=tag, sort=sort)
        return jsonify({'success': True, 'movies': movies})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/search-douban', methods=['GET'])
def search_douban():
    query = request.args.get('q', '')
    try:
        movies = SearchService.search_douban_movies(query)
        return jsonify({'success': True, 'movies': movies})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/check-cookie', methods=['POST'])
def check_cookie():
    data = request.get_json() or {}
    cookie = data.get('cookie', '')
    if not cookie:
        config = load_config()
        cookie = config.get('quark_cookie', '')
    
    valid = QuarkEngine.validate_cookie(cookie)
    return jsonify({'valid': valid})

@app.route('/api/check-channels', methods=['GET'])
def check_channels():
    try:
        config = load_config()
        channels = config.get('telegram_channels', [])
        valid_count, total = SearchService.check_channels_health(channels)
        return jsonify({'success': True, 'valid_count': valid_count, 'total': len(channels) if channels else total})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/subscriptions', methods=['GET', 'POST', 'DELETE'])
def handle_subscriptions():
    if request.method == 'GET':
        subs = SubscriptionManager.get_all()
        return jsonify({'success': True, 'subscriptions': subs})
    
    if request.method == 'POST':
        data = request.get_json() or {}
        SubscriptionManager.add_subscription(data)
        return jsonify({'success': True, 'message': '追剧任务添加成功'})
    
    if request.method == 'DELETE':
        sub_id = request.args.get('id')
        SubscriptionManager.delete_subscription(sub_id)
        return jsonify({'success': True, 'message': '追剧任务已删除'})

@app.route('/api/subscriptions/run-now', methods=['POST'])
def run_subscription_now():
    data = request.get_json() or {}
    sub_id = data.get('id')
    try:
        result = SubscriptionManager.run_single(sub_id)
        return jsonify({'success': True, 'message': '任务执行完毕', 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/search-candidates', methods=['POST'])
def search_candidates():
    data = request.get_json() or {}
    movies = data.get('movies', [])
    cookie = data.get('cookie', '')
    if not cookie:
        config = load_config()
        cookie = config.get('quark_cookie', '')

    try:
        candidates_map = SearchService.search_candidates_for_movies(movies, cookie)
        return jsonify({'success': True, 'candidates_map': candidates_map})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/transfer-selected', methods=['POST'])
def transfer_selected():
    data = request.get_json() or {}
    movie = data.get('movie', {})
    candidate = data.get('candidate', {})
    cookie = data.get('cookie', '')
    target_fid = data.get('target_fid', '0')

    if not cookie:
        config = load_config()
        cookie = config.get('quark_cookie', '')

    try:
        success, msg = QuarkEngine.transfer_candidate(movie, candidate, cookie, target_fid)
        return jsonify({'success': success, 'message': msg})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/proxy-img', methods=['GET'])
def proxy_img():
    url = request.args.get('url', '')
    if not url:
        return "No URL", 400
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=10)
        return resp.content, resp.status_code, {'Content-Type': resp.headers.get('Content-Type', 'image/jpeg')}
    except Exception as e:
        return str(e), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
