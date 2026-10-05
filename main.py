import os
import requests
from flask import Flask, render_template, request, jsonify, Response
from quark_engine import QuarkEngine
from search_service import SearchService
from utils import load_channels, save_channels, DOUBAN_HEADERS

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/get-movies', methods=['GET'])
def get_movies():
    cat_type = request.args.get('type', 'movie')
    mapping = {
        'movie': ('movie', '热门'),
        'tv': ('tv', '热门'),
        'show': ('tv', '综艺'),
        'anime': ('tv', '动漫')
    }
    db_type, db_tag = mapping.get(cat_type, ('movie', '热门'))
    url = f"https://movie.douban.com/j/search_subjects?type={db_type}&tag={db_tag}&page_limit=100&page_start=0"
    
    try:
        resp = requests.get(url, headers=DOUBAN_HEADERS, timeout=10)
        if resp.status_code == 200:
            subjects = resp.json().get('subjects', [])
            movies = [{
                'title': item.get('title'),
                'cover': item.get('cover'),
                'rate': item.get('rate') if item.get('rate') else '暂无',
                'url': item.get('url', f"https://movie.douban.com/subject/{item.get('id')}/")
            } for item in subjects]
            return jsonify({'success': True, 'movies': movies})
        return jsonify({'success': False, 'movies': []})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'movies': []})

@app.route('/api/search-douban', methods=['GET'])
def search_douban():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'success': False, 'movies': []})
    url = f"https://movie.douban.com/j/subject_suggest?q={requests.utils.quote(query)}"
    try:
        resp = requests.get(url, headers=DOUBAN_HEADERS, timeout=10)
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
        return jsonify({'valid': valid, 'message': 'Cookie 有效' if valid else 'Cookie 已失效或格式错误'})
    except Exception as e:
        return jsonify({'valid': False, 'message': f'校验出错: {str(e)}'})

@app.route('/api/channels', methods=['GET', 'POST'])
def handle_channels():
    if request.method == 'POST':
        channels = request.json.get('channels', [])
        save_channels(channels)
        return jsonify({'success': True})
    return jsonify({'success': True, 'channels': load_channels()})

@app.route('/api/transfer', methods=['POST'])
def transfer():
    try:
        data = request.json or {}
        movies = data.get('movies', [])
        cookie = data.get('cookie', '')
        folder_id = data.get('folderId', '0')

        if not movies or not cookie:
            return jsonify({'success': False, 'message': '参数不完整，请检查勾选与 Cookie'})

        service = SearchService(cookie)
        channels = load_channels()
        results = service.batch_search_and_transfer(movies, channels, target_fid=folder_id)
        return jsonify({'success': True, 'results': results})
    except Exception as e:
        return jsonify({'success': False, 'message': f'后台处理异常: {str(e)}'})

@app.errorhandler(Exception)
def handle_exception(e):
    # 强制将所有未捕获异常以 JSON 格式返回，防止返回 HTML 导致 Lucky 触发 502
    return jsonify({'success': False, 'message': f'系统错误: {str(e)}'}), 200

@app.route('/api/proxy-img')
def proxy_img():
    img_url = request.args.get('url')
    if not img_url:
        return Response("Missing url", status=400)
    try:
        resp = requests.get(img_url, headers=DOUBAN_HEADERS, timeout=10)
        return Response(resp.content, mimetype=resp.headers.get('content-type', 'image/jpeg'))
    except Exception:
        return Response("", status=404)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
