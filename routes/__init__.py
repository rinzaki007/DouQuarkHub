from flask import Blueprint

# 创建三个功能蓝图
auth_bp = Blueprint('auth', __name__)
views_bp = Blueprint('views', __name__)
api_bp = Blueprint('api', __name__)

# 导入路由具体实现，避免循环引用
from routes import auth, views, api
