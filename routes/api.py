# routes/api.py
from flask import Blueprint, request, jsonify
import requests
import json
import os
from quark_engine import QuarkEngine
from search_service import SearchService
from subscription_manager import SubscriptionManager

api_bp = Blueprint('api', __name__)

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

@api_bp.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    if request.method == 'GET':
        config = load_config()
        return jsonify({'success': True, 'config': config})
    
    data = request.get_json() or {}
    config = load_config()
    config.update(data)
    save_config(config)
    return jsonify({'success': True, 'message': '配置保存成功'})

@api_bp.route('/api/get-movies', methods=['GET'])
def get_movies():
    tag = request.args.get('tag', '电影')
    sort = request.args.get('sort', 'U')
    try:
        movies = SearchService.get_douban_movies(tag=tag, sort=sort)
        return jsonify({'success': True, 'movies': movies})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@api_bp.route('/api/search-douban', methods=['GET'])
def search_douban():
    query = request.args.get('q', '')
    try:
        movies = SearchService.search_douban_movies(query)
        return jsonify({'success': True, 'movies': movies})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@api_bp.route('/api/check-cookie', methods=['POST'])
def check_cookie():
    data = request.get_json() or {}
    cookie = data.get('cookie', '')
    if not cookie:
        config = load_config()
        cookie = config.get('quark_cookie', '')
    
    valid = QuarkEngine.validate_cookie(cookie)
    return jsonify({'valid': valid})

@api_bp.route('/api/check-channels', methods=['GET'])
def check_channels():
    try:
        config = load_config()
        channels = config.get('telegram_channels', [])
        valid_count, total = SearchService.check_channels_health(channels)
        return jsonify({'success': True, 'valid_count': valid_count, 'total': len(channels) if channels else total})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@api_bp.route('/api/subscriptions', methods=['GET', 'POST', 'DELETE'])
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

@api_bp.route('/api/subscriptions/run-now', methods=['POST'])
def run_subscription_now():
    data = request.get_json() or {}
    sub_id = data.get('id')
    try:
        result = SubscriptionManager.run_single(sub_id)
        return jsonify({'success': True, 'message': '任务执行完毕', 'result': result})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@api_bp.route('/api/search-candidates', methods=['POST'])
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

@api_bp.route('/api/transfer-selected', methods=['POST'])
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

@api_bp.route('/api/proxy-img', methods=['GET'])
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
