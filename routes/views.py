from flask import render_template, session, redirect, url_for
from routes import views_bp
from routes.auth import load_auth

@views_bp.route('/')
def index():
    username_saved, _ = load_auth()
    if not username_saved:
        return redirect(url_for('auth.login'))
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    return render_template('index.html')

@views_bp.route('/admin')
def admin():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    return render_template('admin.html')

@views_bp.route('/openlist')
def openlist():
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    return render_template('openlist.html') if os.path.exists('templates/openlist.html') else "OpenList 页面未配置"
