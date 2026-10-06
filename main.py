from flask import Flask, session, redirect, url_for, request, jsonify
from routes import auth_bp, views_bp, api_bp
from routes.auth import load_auth

app = Flask(__name__)
# 固定一个固定的 secret_key，防止重启后 Session 丢失、登录态失效
app.secret_key = 'moviesync-secure-static-secret-key-2026'

# 注册三大蓝图模块
app.register_blueprint(auth_bp)
app.register_blueprint(views_bp)
app.register_blueprint(api_bp)

# 全局鉴权拦截器
@app.before_request
def require_login():
    username_saved, _ = load_auth()
    
    # 静态资源、登录页、初始化接口直接放行
    allowed_prefixes = ['/login', '/api/setup', '/static']
    if any(request.path.startswith(p) for p in allowed_prefixes):
        return None
        
    # 如果系统尚未初始化账号密码，强制跳转登录/初始化页
    if not username_saved and request.endpoint != 'auth.login' and not request.path.startswith('/api/'):
        return redirect(url_for('auth.login'))
        
    # 检查登录态
    if not session.get('logged_in'):
        # 如果是 API 请求，绝对不能返回 HTML 重定向，必须返回标准的 JSON 401 错误！
        if request.path.startswith('/api/'):
            return jsonify({"success": False, "message": "未登录或会话已过期，请重新登录"}), 401
        # 普通页面请求则跳转登录页
        return redirect(url_for('auth.login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
