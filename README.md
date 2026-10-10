# 🎬 MovieSync

> 豆瓣影视发现 · PanSou / Telegram 资源检索 · 夸克网盘转存 · 自动追剧

MovieSync 是一个面向家庭服务器、NAS 和 Docker 环境的轻量级自托管影视资源管理工具。它以任务中心串联影视搜索、资源筛选、夸克网盘转存与自动追更，让日常操作和后台执行状态更清晰、可追踪。

**核心流程：** 搜索影视 → 通过内置 PanSou 与已配置的 Telegram 频道检索资源 → 选择分享及文件 → 转存到夸克网盘 → 通过自动追剧任务持续检查后续集数。

项目采用可扩展的资源来源抽象和独立的存储目标设计；当前内置 PanSou、Telegram 资源来源与夸克网盘存储实现。Docker 镜像已将 PanSou 搜索 API 一并打包，无需额外创建 PanSou 容器。MovieSync 本身不提供、托管或分发影视文件，具体资源及第三方服务均由使用者自行配置。

## ✨ 当前能力

- 🎬 浏览和搜索豆瓣电影、电视剧、综艺、动漫
- 🔌 资源来源抽象层：内置 PanSou 搜索 API 与 Telegram，可扩展其他来源
- ❤️ 资源源健康检查与最近状态记录
- 🔎 从已配置的资源来源检索候选资源
- ☁️ 解析夸克网盘分享并选择需要的文件
- 📁 将选定资源提交到指定的夸克目录
- 🤖 自动追剧：周期性检查并跟进后续内容
- 📋 独立任务中心：进度、阶段、成功/跳过/失败、日志、重试
- 🔐 管理员认证、CSRF、防暴力登录、敏感配置脱敏
- 💾 JSON 持久化，适合家庭服务器 / NAS / iStoreOS / Docker
- 🐳 提供 GitHub Actions 自动测试与 Docker 镜像构建

## 🛡️ 可靠性与异常恢复

MovieSync 的后台任务不仅关注“执行成功”，也会尽量避免异常情况下重复转存或丢失进度：

- **同一订阅单次执行**：手动检查与定时调度共享运行标记，避免同一订阅同时进入两次检查。
- **转存进度持久化**：追剧记录保存在 `/app/data/subscriptions.json`；成功记录与待处理状态在同一次存储提交中更新。
- **不确定结果保护**：如果远程转存请求可能已到达网盘、但客户端无法确认结果，会保留待核实信息，不直接盲目重试。
- **重启恢复**：服务启动时检查上次中断的任务；存在待确认转存记录时要求先核实网盘结果。
- **任务状态可追踪**：任务中心记录状态、阶段、运行历史与错误摘要，便于定位问题。

这些机制用于降低重复操作和状态丢失的风险，并不替代定期备份 `/app/data`。更新容器前仍建议备份重要配置与任务记录。

## 🧩 开放资源源架构

MovieSync 不把任何单一资源来源写死在核心业务里。

当前结构：

```text
MovieSync
├── 影视信息
│   └── Douban
│
├── ResourceSource
│   ├── PanSou（内置搜索 API）
│   ├── Telegram（内置）
│   └── 其他来源（可扩展）
│
├── 资源候选
│
├── Storage / Transfer
│   └── Quark（当前存储目标）
│
└── Task Center
```

资源源统一位于：

```text
moviesync/services/resource_sources.py
```

核心接口为 `ResourceSource`。

以后增加新的资源来源时，原则上只需要实现：

- 资源搜索
- 资源源健康检查
- 统一的候选资源字段

而不需要重新修改首页、资源选择页、任务中心和转存流程。

这意味着 Telegram 即使未来不可用，也不会影响 MovieSync 的整体架构；只需要增加或替换一个资源源实现即可。

> PanSou API 已随 MovieSync Docker 镜像一起启动；默认地址为容器内的 `http://127.0.0.1:8888`。无需单独部署 PanSou。若已有自己的 PanSou 服务，仍可在 PanSou 卡片里改用外部地址。

## 🩺 资源源健康状态

后台的“资源来源”区域可以手动检查来源状态。

状态包括：

- 🟢 正常：来源可用
- 🟡 部分可用：例如部分 Telegram 频道不可用
- 🔴 不可用：来源整体不可用
- ⚪ 未检查：尚未执行健康检查

健康信息会持久化保存，包括最近检查时间、最近成功时间和失败次数。

健康检查用于帮助判断“是 MovieSync 出问题，还是外部资源来源出了问题”，不会把某个来源视为系统永久依赖。

## 🏗️ 项目结构

```text
MovieSync/
├── moviesync/
│   ├── clients/
│   │   ├── douban.py
│   │   ├── http.py
│   │   ├── quark.py
│   │   └── telegram.py
│   │
│   ├── services/
│   │   ├── resource_sources.py  # 开放资源源抽象与健康检查
│   │   ├── search.py            # 候选资源处理与转存
│   │   ├── subscriptions.py     # 自动追剧
│   │   └── tasks.py             # 任务中心
│   │
│   ├── web/
│   │   └── routes.py
│   ├── app.py
│   ├── auth.py
│   ├── config_store.py
│   ├── logging_setup.py
│   ├── settings.py
│   └── storage.py
│
├── static/
├── templates/
├── tests/
├── Dockerfile
├── main.py
└── README.md
```

## 🐳 Docker 部署

### Docker Compose

新建 `docker-compose.yml`：

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
      - MOVIESYNC_COOKIE_SECURE=0
```

启动：

```bash
docker compose up -d
```

访问：

```text
http://你的服务器IP:8099
```

第一次启动会进入管理员初始化页面。MovieSync 容器会同时启动内置 PanSou 搜索 API；PanSou 缓存写入 `/app/data/pansou/cache`，随现有 `/app/data` 挂载持久化。

### iStoreOS / NAS

例如：

```text
/mnt/sata1-1/moviesync -> /app/data
```

只要 `/app/data` 挂载目录保持不变，更新容器不会丢失账号、配置和追剧任务。

### 直接 Docker

```bash
docker run -d \
  --name MovieSync \
  --restart unless-stopped \
  -p 8099:5000 \
  -v /你的目录/moviesync:/app/data \
  -e TZ=Asia/Shanghai \
  -e MOVIESYNC_COOKIE_SECURE=0 \
  ghcr.io/rinzaki007/moviesync:latest
```

## ⚙️ 初次配置

1. 创建管理员账号
2. 登录后台
3. 配置夸克 Cookie
4. 设置默认 FID / 分类 FID
5. 在「卡片管理」中启用 PanSou（默认地址已内置，无需填写）
6. 如需额外搜索 Telegram，再配置对应频道
7. 使用首页搜索影视
8. 选择候选资源和文件
9. 提交转存任务
10. 需要时创建自动追剧任务

## 💾 数据目录

运行数据保存在：

```text
/app/data/
├── auth.json
├── config.json
├── subscriptions.json
├── tasks.json
├── .secret_key
└── logs/
```

这些内容属于运行数据，不应提交到 GitHub。

配置文件会自动维护 schema version，并兼容旧版本配置。

## 🔧 常用命令

查看容器：

```bash
docker ps | grep MovieSync
```

查看日志：

```bash
docker logs -f MovieSync
```

重启：

```bash
docker restart MovieSync
```

更新：

```bash
docker compose pull
docker compose up -d
```

## 🛡️ 设计原则

MovieSync 的核心设计目标不是绑定某一个资源网站，而是：

1. **来源可替换**：ResourceSource 与核心业务解耦
2. **存储可替换**：资源发现与存储目标解耦
3. **失败可解释**：区分来源、解析、转存和任务执行错误
4. **状态可追踪**：统一任务中心记录后台任务
5. **数据可持久化**：容器更新不依赖容器内部文件
6. **最小信任**：浏览器提交的资源参数在服务端重新验证
7. **易于维护**：尽量保持单一职责和明确的 Provider 边界

## ⚠️ 免责声明

MovieSync 是一个通用的软件平台，不提供、托管或分发影视资源内容。

资源来源、账号、链接、文件以及具体使用方式均由使用者自行配置和决定。使用者应自行确认相关内容的合法性，并遵守所在地法律法规、版权要求以及相关服务的平台规则和服务条款。

项目作者不对使用者配置的第三方服务、外部资源来源、账号状态、数据损失或具体使用行为承担责任。

## 📄 License

MIT License
