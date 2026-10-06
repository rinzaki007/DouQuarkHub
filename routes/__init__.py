from flask import Blueprint

# 创建三个功能蓝图
auth_bp = Blueprint('auth', __name__)
views_bp = Blueprint('views', __name__)
api_bp = Blueprint('api', __name__)

# 使用相对导入（加点 .），避免循环导入和包路径冲突
from . import auth, views, api
