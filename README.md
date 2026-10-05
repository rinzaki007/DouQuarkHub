### 📂 项目目录与文件说明

| 文件 / 路径 | 核心功能与技术说明 |
| :--- | :--- |
| **cloudmovie/** | 项目根目录 |
| ├── **.github/workflows/** | GitHub Actions 自动化流水线配置 |
| │   └── `docker-build.yml` | 自动构建镜像并进行并发控制 |
| ├── **templates/** | 前端页面模板目录 |
| │   └── `index.html` | 纯 HTML 页面（吸顶栏、8列网格、状态监控、配置弹窗） |
| ├── **static/** | 静态资源目录 |
| │   ├── **css/** | 样式表目录 |
| │   │   └── `style.css` | 页面全套 CSS 样式 |
| │   └── **js/** | 脚本目录 |
| │       └── `main.js` | 前端交互与 API 逻辑（ReadableStream 流式日志读取） |
| ├── `main.py` | Flask 主程序（全局 JSON 防错、流式日志响应） |
| ├── `quark_engine.py` | 夸克 API 核心（Cookie 校验、Token 申请、两步解析与转存） |
| ├── `search_service.py` | TG 频道多线程并发检索与流式转存调度 |
| ├── `requirements.txt` | Python 依赖包清单 |
| └── `Dockerfile` | Docker 镜像构建文件 |



docker-compose部署

version: "3"
services:
  mycloudcore:
    image: ghcr.io/rinzaki007/mycloudcore:latest
    container_name: my-cloud-core
    ports:
      - 8099:5000
    volumes:
      - （存储地址）默认 ./data:/app/data
    restart: always
