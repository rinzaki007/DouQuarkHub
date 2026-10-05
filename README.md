### 📂 项目目录与文件说明

| 文件 / 路径 | 核心功能与技术说明 |
| :--- | :--- |
| **DouQuarkHub/** | 项目根目录 |
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



## 🚀 快速部署 (Docker Compose)

推荐使用 Docker Compose 进行部署，只需两步即可完成。

### 1. 编写配置文件
在服务器任意目录下创建一个名为 `docker-compose.yml` 的文件，并粘贴以下内容：

```yaml
version: "3.8"

services:
  mycloudcore:
    image: ghcr.io/rinzaki007/mycloudcore:latest
    container_name: my-cloud-core
    restart: always
    ports:
      - "8099:5000"
    volumes:
      - ./data:/app/data
    environment:
      - TZ=Asia/Shanghai
