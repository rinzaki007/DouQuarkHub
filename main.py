import requests
import urllib.parse
from flask import Flask, render_template, request, jsonify, Response
from utils import load_channels, save_channels, DOUBAN_HEADERS
from search_service import execute_transfer_logic

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/get-movies')
def get_movies():
    m_type = request.args.get('type', 'movie')
    tag = '热门'
    url = f"https://movie.douban.com/j/search_subjects?type={m_type}&tag={urllib.parse.quote(tag)}&page_limit=50&page_start=0"
    try:
        res = requests.get(url, headers=DOUBAN_HEADERS, timeout=8)
        if res.status_code == 200:
            data = res.json()
            subjects = data.get("subjects", [])
            movies = []
            for item in subjects:
                movies.append({
                    "title": item.get("title", ""),
                    "rate": item.get("rate", ""),
                    "cover": item.get("cover", "")
                })
            return jsonify({"success": True, "movies": movies})
        return jsonify({"success": False, "movies": [], "message": f"豆瓣响应 HTTP {res.status_code}"})
    except Exception as e:
        return jsonify({"success": False, "movies": [], "message": str(e)})

@app.route('/api/search-douban')
def search_douban():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({"success": True, "movies": []})
    
    url = f"https://movie.douban.com/j/subject_suggest?q={urllib.parse.quote(query)}"
    try:
        res = requests.get(url, headers=DOUBAN_HEADERS, timeout=8)
        if res.status_code == 200:
            data = res.json()
            movies = []
            for item in data:
                if isinstance(item, dict) and item.get("type") in ["movie", "tv", "sub"]:
                    movies.append({
                        "title": item.get("title", ""),
                        "rate": item.get("year", ""),
                        "cover": item.get("img", "")
                    })
            return jsonify({"success": True, "movies": movies})
        return jsonify({"success": False, "movies": [], "message": f"豆瓣搜索 HTTP {res.status_code}"})
    except Exception as e:
        return jsonify({"success": False, "movies": [], "message": str(e)})

@app.route('/api/proxy-img')
def proxy_img():
    img_url = request.args.get('url', '')
    if not img_url:
        return Response("", status=404)
    try:
        res = requests.get(img_url, headers=DOUBAN_HEADERS, timeout=6)
        if res.status_code == 200:
            return Response(res.content, mimetype=res.headers.get('Content-Type', 'image/jpeg'))
        return Response("", status=res.status_code)
    except Exception:
        return Response("", status=500)

@app.route('/api/channels', methods=['GET', 'POST'])
def api_channels():
    if request.method == 'GET':
        return jsonify({"success": True, "channels": load_channels()})
    else:
        data = request.json or {}
        channels = data.get("channels", [])
        if save_channels(channels):
            return jsonify({"success": True, "message": "频道保存成功"})
        return jsonify({"success": False, "message": "保存频道文件失败"})

@app.route('/api/transfer', methods=['POST'])
def api_transfer():
    data = request.json or {}
    movies = data.get("movies", [])
    cookie = data.get("cookie", "")
    folder_id = data.get("folderId", "0")

    if not movies:
        return jsonify({"success": False, "message": "未传入任何目标"})
    if not cookie:
        return jsonify({"success": False, "message": "未提供夸克 Cookie"})

    results = {}
    for movie in movies:
        logs = execute_transfer_logic(movie, cookie, folder_id)
        results[movie] = logs

    return jsonify({"success": True, "results": results})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
