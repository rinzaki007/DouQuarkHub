from flask import Flask, session, redirect, url_for
from routes import auth_bp, views_bp, api_bp
from routes.auth import load_auth

app = Flask(__name__)
app.secret_key = 'moviesync-secret-key-change-it'  # 建议换成随机密钥

# 注册三大蓝图模块
app.register_blueprint(auth_bp)
app.register_blueprint(views_bp)
app.register_blueprint(api_bp)

# 全局鉴权拦截器
@app.before_request
def require_login():
    from flask import request
    username_saved, _ = load_auth()
    # 静态资源和登录/初始化接口放行
    allowed_paths = ['/login', '/api/setup', '/static']
    if not username_saved and request.path not in ['/login', '/api/setup']:
        return redirect(url_for('auth.login'))
    
    if any(request.path.startswith(p) for p in allowed_paths):
        return None
        
    if not session.get('logged_in') and request.endpoint not in ['auth.login', 'auth.setup']:
        if request.path.startswith('/api/'):
            return {"success": False, "message": "未登录或会话已过期"}, 401
        return redirect(url_for('auth.login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
