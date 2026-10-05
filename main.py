import os
import requests
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from concurrent.futures import ThreadPoolExecutor
from quark_engine import QuarkEngine
from search_service import SearchService
from utils import load_channels, save_channels, DOUBAN_HEADERS

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/get-movies', methods=['GET'])
def get_movies():
    main_tag = request.args.get('tag', '电影')   # 电影, 电视剧, 综艺, 动漫
    sort_type = request.args.get('sort', 'U')    # U: 热门, R: 最新上映, S: 高分, T: 最多评价
    genre = request.args.get('genre', '')        # 动作, 喜剧...
    country = request.args.get('country', '')    # 中国大陆, 美国...
    year_range = request.args.get('year', '')    # 2026,2026 或 2020,2029

    # 豆瓣 API 中动漫对应的标准 tag 为 '动画'
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
        return jsonify({'success': False, 'movies': [], 'message': f'豆瓣返回 {resp.status_code}'})
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

@app.route('/api/check-channels', methods=['GET'])
def check_channels_health():
    channels = load_channels()
    if not channels:
        return jsonify({'success': True, 'total': 0, 'valid_count': 0})

    def test_channel(ch):
        ch_id = ch.get('id', '').strip()
        if not ch_id:
            return False
        url = f"https://t.me/s/{ch_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        try:
            resp = requests.head(url, headers=headers, timeout=2.0)
            return resp.status_code == 200
        except Exception:
            return False

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(test_channel, channels))

    valid_count = sum(1 for is_valid in results if is_valid)
    return jsonify({
        'success': True,
        'total': len(channels),
        'valid_count': valid_count
    })

@app.route('/api/channels', methods=['GET', 'POST'])
def handle_channels():
    if request.method == 'POST':
        channels = request.json.get('channels', [])
        save_channels(channels)
        return jsonify({'success': True})
    return jsonify({'success': True, 'channels': load_channels()})

@app.route('/api/transfer', methods=['POST'])
def transfer():
    data = request.json or {}
    movies = data.get('movies', [])
    cookie = data.get('cookie', '')
    folder_id = data.get('folderId', '0')

    if not movies or not cookie:
        return Response("❌ 参数不完整，请检查勾选与 Cookie\n", mimetype='text/plain; charset=utf-8')

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
        resp = requests.get(img_url, headers=DOUBAN_HEADERS, timeout=10)
        return Response(resp.content, mimetype=resp.headers.get('content-type', 'image/jpeg'))
    except Exception:
        return Response("", status=404)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
