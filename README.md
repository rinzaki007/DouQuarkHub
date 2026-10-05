cloudmovie/
├── .github/
│   └── workflows/
│       └── docker-build.yml      # GitHub Actions 自动化构建与并发控制
├── templates/
│   └── index.html               # 页面结构（吸顶栏、8列网格、状态监控、配置弹窗）
├── static/
│   ├── css/
│   │   └── style.css            # 页面全套 CSS 样式
│   └── js/
│       └── main.js              # 前端交互逻辑（ReadableStream 流式日志读取）
├── main.py                      # Flask 主程序（全局 JSON 防错、流式日志响应）
├── quark_engine.py              # 夸克 API 核心（Cookie 校验、Token 申请、两步解析与转存）
└── search_service.py            # TG 频道多线程并发检索与流式转存调度




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
