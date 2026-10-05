import os
import requests
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from quark_engine import QuarkEngine, clean_tv_filename
from subscription_manager import SubscriptionManager
from search_service import SearchService
from utils import load_channels, save_channels, DOUBAN_HEADERS

app = Flask(__name__)

# 全局获取夸克 Cookie 函数1
def get_global_cookie():
    return request.headers.get('X-Quark-Cookie', '')

# 初始化追剧轮询调度引擎
sub_manager = SubscriptionManager(get_cookie_func=lambda: app.config.get('QUARK_COOKIE', ''))
sub_manager.start_scheduler()

@app.route('/')
def index():
    return render_template('index.html')

# 🔍 1. 选集转存接口：解析分享链接中的所有文件并进行洗剧预览
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

# 🚀 2. 选集转存提交接口：仅转存勾选的资源
@app.route('/api/save-selected-files', methods=['POST'])
def save_selected_files():
    data = request.json or {}
    pwd_id = data.get('pwd_id')
    stoken = data.get('stoken')
    selected_fids = data.get('fids', [])
    target_fid = data.get('target_fid', '0')
    cookie = data.get('cookie', '')

    if not selected_fids or not cookie:
        return jsonify({'success': False, 'message': '未选择任何文件'})

    engine = QuarkEngine(cookie)
    files_to_save = [{'fid': fid} for fid in selected_fids]
    
    ok, msg = engine.save_files(pwd_id, files_to_save, stoken, target_fid)
    return jsonify({'success': ok, 'message': msg})

# 📺 3. 追剧订阅 CRUD 接口
@app.route('/api/subscriptions', methods=['GET', 'POST', 'DELETE'])
def handle_subscriptions():
    if request.method == 'GET':
        return jsonify({'success': True, 'subscriptions': sub_manager.get_subscriptions()})

    if request.method == 'POST':
        data = request.json or {}
        # 设置全局 Cookie 供轮询引擎使用
        app.config['QUARK_COOKIE'] = data.get('cookie', '')
        
        new_sub = sub_manager.add_subscription(
            title=data.get('title'),
            pwd_id=data.get('pwd_id'),
            target_fid=data.get('target_fid', '0'),
            interval_hours=data.get('interval_hours', 6)
        )
        return jsonify({'success': True, 'subscription': new_sub})

    if request.method == 'DELETE':
        sub_id = request.args.get('id')
        sub_manager.delete_subscription(sub_id)
        return jsonify({'success': True})

# 🔄 4. 立即检查追剧更新接口
@app.route('/api/subscriptions/run-now', methods=['POST'])
def run_sub_now():
    data = request.json or {}
    sub_id = data.get('id')
    cookie = data.get('cookie', '')
    if cookie:
        app.config['QUARK_COOKIE'] = cookie
        
    ok, msg = sub_manager.check_subscription_now(sub_id)
    return jsonify({'success': ok, 'message': msg})

# 兼容原项目的豆瓣分类获取、频道列表和流式批量转存等 API...
# (省略保持不变的部分代码)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
