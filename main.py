import os
import json
import requests
from flask import Flask, request, jsonify, render_template
# 假设你的核心搜索和转存逻辑封装在 search_service 中
# from search_service import SearchService, log_system, load_full_config

app = Flask(__name__)

# 示例配置加载函数（请根据你实际的项目结构调整）
def load_full_config():
    config_path = 'config.json'
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "quark_cookie": "",
        "default_fid": "0",
        "category_fids": {
            "电影": "",
            "电视剧": "",
            "综艺": "",
            "动漫": ""
        }
    }

def log_system(msg):
    print(f"[System Log] {msg}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/config', methods=['GET'])
def api_get_config():
    config = load_full_config()
    return jsonify({'success': True, 'config': config})

# 🎯 核心修改：支持接收前端传过来的自定义目标目录 target_fid
@app.route('/api/transfer-selected', methods=['POST'])
def api_transfer_selected():
    data = request.json or {}
    movie = data.get('movie')
    candidate = data.get('candidate')
    target_fid_override = data.get('target_fid')  # 接收前端传过来的自定义目录 FID
    config = load_full_config()
    cookie = data.get('cookie', '').strip() or config.get('quark_cookie', '')
    
    if not movie or not candidate:
        return jsonify({'success': False, 'message': '参数不完整'})
    if not cookie:
        return jsonify({'success': False, 'message': '未配置夸克 Cookie'})

    # 实例化你的转存服务（请确保 SearchService 已正确导入）
    # service = SearchService(cookie)
    
    # 如果用户指定了目录则直接使用，否则走原有的 category_fids 自动匹配
    default_fid = target_fid_override or config.get('default_fid', '0')
    category_fids = {} if target_fid_override else config.get('category_fids', {})

    title = movie.get('title', '未知影片') if isinstance(movie, dict) else str(movie)
    log_system(f"用户已确认选择，开始转存《{title}》...")

    # 调起底层转存方法
    # success, msg = service.transfer_selected_resource(
    #     movie=movie,
    #     candidate=candidate,
    #     target_fid=default_fid,
    #     category_fids=category_fids
    # )
    
    # 模拟返回（实际请替换为你的 service 调用结果）
    success = True
    msg = f"成功转存《{title}》至指定目录 (FID: {default_fid})"

    log_system(msg)
    if success:
        return jsonify({'success': True, 'message': msg})
    else:
        return jsonify({'success': False, 'message': msg})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
