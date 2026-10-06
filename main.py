from flask import Flask, session, redirect, url_for, request, jsonify
from routes import auth_bp, views_bp, api_bp
from routes.auth import load_auth

app = Flask(__name__)
# 固定 secret_key，防止重启后 Session 丢失、登录态失效
app.secret_key = 'moviesync-secure-static-secret-key-2026'

# 注册蓝图
app.register_blueprint(auth_bp)
app.register_blueprint(views_bp)
app.register_blueprint(api_bp)

@app.before_request
def require_login():
    username_saved, _ = load_auth()
    allowed_prefixes = ['/login', '/api/setup', '/static']
    if any(request.path.startswith(p) for p in allowed_prefixes):
        return None
        
    if not username_saved and request.endpoint != 'auth.login' and not request.path.startswith('/api/'):
        return redirect(url_for('auth.login'))
        
    if not session.get('logged_in'):
        if request.path.startswith('/api/'):
            return jsonify({"success": False, "message": "未登录或会话已过期，请重新登录"}), 401
        return redirect(url_for('auth.login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
