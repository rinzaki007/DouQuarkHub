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
services:
  douquarkhub:
    # 镜像地址。如果国内服务器拉取 ghcr.io 较慢，可自行替换或配置国内镜像加速（例如：ghcr.m.daocloud.io/rinzaki007/mycloudcore:latest）
    image: ghcr.io/rinzaki007/douquarkhub:latest
    container_name: DouQuarkHub
    # 容器重启策略：unless-stopped 表示随系统自动重启，但如果被手动 stop 停止，则不会自动拉起
    restart: unless-stopped
    # 左侧的 8099 为宿主机访问端口（若冲突可修改，如 9000:5000）；右侧的 5000 为容器内应用监听端口，请勿修改
    ports:
      - "8099:5000"
    volumes:
      # 存储地址挂载：请根据你的实际需求修改左侧的宿主机目录路径
      - ./data:/app/data
    environment:
      - TZ=Asia/Shanghai
