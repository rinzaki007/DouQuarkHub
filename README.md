# 🎬 MovieSync

> 豆瓣影视检索 → Telegram 资源匹配 → 夸克网盘转存 → 分类归档 → 自动追剧

MovieSync 是一个面向个人自托管场景的影视资源管理工具。它把影视探索、Telegram 频道检索、夸克分享资源解析、白名单转存和自动追更串成一条完整流程。

## ✨ 功能

- 豆瓣电影 / 电视剧 / 综艺 / 动漫探索与搜索
- 多 Telegram 频道并发检索
- 候选资源聚合与重复分享链接去重
- 具体文件白名单选择后再转存
- 按分类 FID 自动创建影视专属目录
- 自动追剧任务与按任务周期检查
- 后台配置、运行日志、频道健康检查
- Docker 单容器部署

## 🏗️ 项目结构

```text
MovieSync/
├── moviesync/
│   ├── clients/            # 豆瓣 / Telegram / 夸克 / HTTP 客户端
│   ├── services/           # 检索与订阅业务逻辑
│   ├── web/                # Flask 页面和 API
│   ├── auth.py
│   ├── config_store.py
│   ├── logging_setup.py
│   ├── settings.py
│   └── storage.py
├── templates/
├── static/
├── tests/
├── Dockerfile
├── requirements.txt
└── main.py                 # 启动兼容入口
```

详细设计见 [ARCHITECTURE.md](ARCHITECTURE.md)，重构记录见 [REFACTORING.md](REFACTORING.md)。

## 🚀 Docker Compose

```yaml
services:
  moviesync:
    image: ghcr.io/rinzaki007/moviesync:latest
    container_name: MovieSync
    restart: unless-stopped
    ports:
      - "8099:5000"
    volumes:
      - ./data:/app/data
    environment:
      - TZ=Asia/Shanghai
      # HTTPS 反向代理后可设为 1
      - MOVIESYNC_COOKIE_SECURE=0
```

启动后访问：

```text
http://你的服务器IP:8099
```

首次启动会进入管理员初始化页面。

## 🔐 安全说明

运行时配置、管理员认证、Secret Key、Cookie、订阅和日志统一保存在 `data/`。建议对该目录做好权限控制，不要把其中的 JSON 或 `.secret_key` 提交到 Git。

Cookie 不再依赖浏览器 `localStorage`。前端配置接口只返回 Cookie 是否已配置；真正调用夸克接口时由服务端读取 Cookie。

转存请求不会信任浏览器传入的 `stoken`。服务端会重新解析分享源，并验证用户所选文件是否确实存在于该分享中。

## 🧪 本地测试

安装开发依赖：

```bash
pip install -r requirements-dev.txt
pytest -q
```

当前源码包已完成静态编译检查和底层单元测试。由于测试环境没有可用的真实 Telegram / 豆瓣 / 夸克账号，不会在测试阶段调用真实上游服务。

## 🔄 从旧版升级

旧版本的 `auth.json` / `config.json` 可以在首次启动新版本时自动迁移到 `data/`；旧的 `data/channels.json` 也会尝试合并进统一配置。

升级后建议检查后台的：

1. 夸克 Cookie
2. 默认 FID 与分类 FID
3. Telegram 频道
4. 自动追剧任务

旧的顶层 Python 模块保留了兼容适配层，不需要手动修改原有启动命令。

## ⚠️ 免责声明

本项目仅供个人学习、技术研究和交流使用。使用者应自行遵守当地法律法规、版权要求以及相关平台服务条款。项目作者不对因使用本项目产生的数据损失、账号风险或其他后果承担责任。

## 📄 License

MIT License
