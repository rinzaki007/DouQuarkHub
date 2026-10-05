# 🎬 MovieSync

<p align="center">
  <b>豆瓣影视流检索与夸克网盘自动转存系统</b>
</p>

---

## 💡 项目简介

**MovieSync** 是一个集成豆瓣 API 与夸克网盘的高效影视资源流转工具。

- **核心功能**：
  - 🎥 **豆瓣热榜与全局影视探索**：通过豆瓣 API 实时获取热门影视内容与全局检索。
  - 🔍 **多频道智能匹配**：支持输入关键词后联动已有频道，精准检索对应的影视资源。
  - ☁️ **夸克网盘一键转存**：基于夸克 Cookie 授权，自动完成解析并将资源转存至夸克网盘。
- **特别说明**：本项目**全程由 Gemini AI 协助编译编写**，作者本人对编程和编译属于“零基础小白”水平，属于自用功能。如果在使用过程中遇到 Bug 或不合理的地方，欢迎大家多多包涵！

---



### 📂 项目目录与文件说明

| 文件 / 路径 | 核心功能与技术说明 |
| :--- | :--- |
| **MovieSync/** | 项目根目录 |
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

---



## 🚀 快速部署 (Docker Compose)

推荐使用 Docker Compose 进行部署，只需两步即可完成。

### 1. 编写配置文件
在服务器任意目录下创建一个名为 `docker-compose.yml` 的文件，并粘贴以下内容：

```yaml
services:
  moviesync:
    # 镜像地址。如果国内服务器拉取 ghcr.io 较慢，可自行替换或配置国内镜像加速（例如：ghcr.m.daocloud.io/rinzaki007/mycloudcore:latest）
    image: ghcr.io/rinzaki007/moviesync:latest
    container_name: MovieSync
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
 ```
---
 


📄 免责声明 (Disclaimer)
本项目（MovieSync）仅供个人学习、技术研究与交流使用，严禁用于商业用途或非法牟利行为。

本项目所接入的网盘 API 或相关服务均来自公开渠道，作者不对因使用本项目而产生的任何数据丢失、账号封禁、版权纠纷或法律风险承担任何责任。

用户在使用本项目时，必须严格遵守当地法律法规以及相关平台的服务条款。任何基于本项目二次开发或部署造成的后果，均由使用者自行承担。

如有侵权或违规内容，请通过 Issue 联系作者删除。

📜 开源协议 (License)
本项目采用 MIT License 开源协议进行许可。
