from flask import request, jsonify, session, render_template
from routes import auth_bp
import json
import os
from werkzeug.security import generate_password_hash, check_password_hash

CONFIG_FILE = 'config.json'

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
    data = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except:
            pass
    data['username'] = username
    data['password_hash'] = password_hash
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

@auth_bp.route('/login', methods=['GET', 'POST'])
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

@auth_bp.route('/api/setup', methods=['POST'])
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

@auth_bp.route('/logout')
def logout():
    session.clear()
    return jsonify({'success': True})
