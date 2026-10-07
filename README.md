# 🎬 MovieSync

> 豆瓣影视检索 → Telegram 资源匹配 → 夸克网盘转存 → 分类归档 → 自动追剧

MovieSync 是一个面向个人自托管场景的影视资源管理工具。它把影视探索、Telegram 频道检索、夸克分享资源解析、白名单转存、分类归档和自动追更串成一条完整流程。

---

## ✨ 主要功能

- 🎬 豆瓣电影 / 电视剧 / 综艺 / 动漫浏览与搜索
- 🔎 多 Telegram 频道并发检索影视资源
- 🧩 候选资源聚合，并按夸克分享 ID 去重
- ☑️ 用户选择具体文件后再执行转存，避免整包误转
- 📁 按分类 FID 创建影视专属文件夹并归档
- ❤️ 自动追剧任务，可按周期检查更新
- 🧾 后台实时查看运行日志
- 📡 Telegram 频道健康检查
- 🔐 Session + CSRF + 登录失败限流等基础安全保护
- 🐳 Docker 单容器部署，运行数据独立持久化到 `/app/data`
- 🔄 兼容旧版 `auth.json` / `config.json` / `channels.json` 的迁移

---

## 🏗️ 项目结构

```text
MovieSync/
├── .github/
│   └── workflows/
│       └── docker-build.yml      # GitHub Actions：自动构建/发布 Docker 镜像
│
├── moviesync/
│   ├── clients/
│   │   ├── __init__.py           # 外部客户端包说明
│   │   ├── douban.py             # 豆瓣影视列表、搜索、字段兼容与接口兜底
│   │   ├── http.py               # 通用 HTTP Session、超时、JSON、重试
│   │   ├── quark.py              # 夸克 Cookie、分享解析、建目录、文件转存
│   │   └── telegram.py           # Telegram 频道检查、消息搜索、夸克链接提取
│   │
│   ├── services/
│   │   ├── __init__.py           # 业务服务包说明
│   │   ├── search.py             # 多频道并发检索、候选聚合、白名单转存
│   │   └── subscriptions.py      # 自动追剧、定时检查、更新记录
│   │
│   ├── web/
│   │   ├── __init__.py           # 登录限流、认证前置检查、安全响应头
│   │   └── routes.py             # 页面路由及全部 Flask API
│   │
│   ├── __init__.py               # create_app 兼容导出
│   ├── app.py                    # Flask 应用组装、依赖注入、Session 配置
│   ├── auth.py                   # 管理员初始化、登录、修改用户名/密码
│   ├── config_store.py            # 配置加载、校验、迁移、脱敏
│   ├── logging_setup.py           # 内存/文件/控制台日志
│   ├── settings.py                # 环境变量、数据目录、Secret Key
│   └── storage.py                 # 原子 JSON 持久化
│
├── static/
│   ├── css/style.css              # 主页面公共视觉样式
│   └── js/main.js                 # 主页面交互、API 调用、资源转存、追剧
│
├── templates/
│   ├── admin.html                 # 管理后台
│   ├── index.html                 # 主影视页面
│   └── login.html                 # 初始化/登录页面
│
├── tests/
│   ├── test_config.py             # 配置校验/脱敏测试
│   ├── test_quark_utils.py        # 夸克工具函数测试
│   ├── test_search.py             # 资源检索去重测试
│   ├── test_storage.py             # JSON 原子存储测试
│   └── test_subscription.py       # 自动追剧基础测试
│
├── Dockerfile                     # 生产 Docker 镜像
├── main.py                        # 启动兼容入口
├── pyproject.toml                 # Python 项目/测试配置
├── requirements.txt               # 生产依赖
└── requirements-dev.txt            # 开发测试依赖
```

---

## 🔄 最近版本更新

当前版本主要完成了一轮**结构化重构、稳定性和安全性增强**，并补齐了项目代码说明。

### 1. 数据持久化统一到 `/app/data`

Docker 运行时使用：

```text
/app/data
├── auth.json
├── config.json
├── subscriptions.json
├── .secret_key
└── logs/
    └── moviesync.log
```

Dockerfile 中通过 `MOVIESYNC_DATA_DIR=/app/data` 和 `VOLUME ["/app/data"]` 保证容器内配置和宿主机挂载目录一致。

如果使用 Docker Compose，推荐：

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

### 2. 豆瓣接口增强

电影列表现在采用多级兜底：

1. 移动端 `recent_hot/movie`
2. 移动端 `movie/recommend`
3. 网页 `j/search_subjects`

同时兼容 `subjects`、`items`、`subject_collection_items`、`recommend_items` 以及多种海报/评分字段。

### 3. 修复首页海报渲染中断

近期实际排查发现，豆瓣 API 返回数据正常，但前端因为调用了不存在的 `getNoCoverImage()`，浏览器抛出 `ReferenceError`，导致电影网格停止渲染。

现在 `static/js/main.js` 已补充统一的无海报占位图生成函数，并使用 SVG Data URL，不依赖额外图片文件。

**这就是最近“豆瓣数据正常但页面完全不显示”的真正原因。**

### 4. 转存安全链路增强

转存不再信任浏览器直接提交的 `stoken`。当前流程：

```text
浏览器选择资源
    ↓
提交电影 + 候选资源 + 文件 FID
    ↓
服务端重新解析夸克分享
    ↓
获取新的 stoken
    ↓
验证所选 FID 是否真实存在于该分享
    ↓
创建影视专属文件夹
    ↓
执行白名单文件转存
```

### 5. FID 校验和分类归档

支持默认 FID、电影 FID、电视剧 FID、综艺 FID、动漫 FID，以及手动转存和自动追剧目标 FID。

FID 限制为 `A-Z / a-z / 0-9 / _ / -`，最长 128 个字符。

### 6. 管理员账户安全

现在后台支持修改管理员用户名、修改管理员密码、当前密码验证，以及修改成功后清理 Session 并重新登录。

用户名限制为 2～64 个字符；密码限制为 8～128 个字符。

账户安全区域顺序调整为：

```text
新用户名
↓
当前密码
↓
修改用户名
```

同时补充深色主题输入框和 Chrome Autofill 样式，避免自动填充后出现白色输入框。

### 7. 前端 API 请求统一处理

`static/js/main.js` 中的 `apiFetch()` 统一负责同源 Cookie、CSRF Token 和 API 请求处理。后续新增修改数据接口时，优先复用它。

### 8. JSON 存储稳定性增强

`moviesync/storage.py` 使用临时文件 → flush → fsync → os.replace 的方式写入 JSON，降低程序中断导致配置文件损坏的风险。

### 9. HTTP 请求统一重试

`moviesync/clients/http.py` 统一处理 requests Session、线程隔离、JSON 解析、网络异常以及 429/500/502/503/504 的有限重试和退避。

### 10. 自动追剧

自动追剧任务会记录任务 ID、剧名、分享 ID、目标 FID、检测周期、起始集数、文件白名单、已保存集数、检测时间和最后错误。

后台调度器默认每 30 秒检查一次到期任务，实际执行周期由每个任务自己的设置决定。

### 11. 代码注释与维护说明

本次同步为主要 Python、JS、CSS、HTML、测试、Docker 和项目配置文件补充了文件级用途说明与维护提示，方便以后直接定位“这个文件是干什么的、哪些地方不能随便改”。

---

## 🔐 安全说明

运行时配置统一放在 `data/`，包括管理员认证、Secret Key、夸克 Cookie、FID、Telegram 频道、自动追剧任务和日志。

不要把 `data/auth.json`、`data/config.json`、`data/subscriptions.json`、`data/.secret_key` 提交到 Git。

Cookie 不再依赖浏览器 `localStorage`。前端只会看到 Cookie 是否配置，真正的 Cookie 由服务端读取。

---

## 🧪 本地测试

安装开发依赖：

```bash
pip install -r requirements-dev.txt
```

运行测试：

```bash
pytest -q
```

测试主要覆盖配置校验、频道规范化、夸克工具函数、JSON 原子存储、资源搜索去重和自动追剧基础逻辑。真实 Telegram / 豆瓣 / 夸克接口不会在单元测试阶段调用。

---

## 🚀 Docker 部署

```bash
docker compose up -d
```

查看日志：

```bash
docker logs -f MovieSync
```

访问 `http://你的服务器IP:8099`。首次启动进入管理员初始化页面。

---

## 💾 iStoreOS / Docker 持久化

如果使用 iStoreOS，推荐将 MovieSync 数据目录单独挂载，例如：

```text
/mnt/sata1-1/moviesync -> /app/data
```

这样删除容器、重建镜像或更新镜像都不会因为容器本身被替换而丢失账号、Cookie、任务和 Secret Key。

**不要把 MovieSync 的配置文件只保存在容器内部。**

---

## 🔄 从旧版升级

旧版本的 `auth.json` / `config.json` / `channels.json` 可以在新版本首次启动时自动迁移。

升级后建议检查：

1. 夸克 Cookie
2. 默认 FID
3. 分类 FID
4. Telegram 频道
5. 自动追剧任务
6. OpenList 地址

---

## 🧭 页面空白排查

如果以后再次遇到“页面不显示”，建议：

1. 浏览器先访问 `/api/get-movies?tag=电影&sort=U`，确认返回 `success: true` 和 `movies`。
2. 按 `F12 → Console` 查看是否有 JavaScript `ReferenceError` / `TypeError`。
3. 最后执行 `docker logs MovieSync` 查看后端异常。

如果 API 正常、Docker 也正常而页面空白，大概率是浏览器端 JavaScript 渲染错误。

---

## 📌 开发维护原则

1. 业务逻辑放 Python 服务层，不要全部塞进 Flask 路由。
2. 外部 API 调用统一经过 `clients/`。
3. 持久化数据统一通过 `JsonStore`。
4. 前端 API 请求优先使用 `apiFetch()`。
5. 所有修改数据的 API 保留 CSRF 保护。
6. 浏览器传入的 FID、文件 ID、stoken 等参数不能直接信任。
7. 新增配置字段时，同时考虑旧配置迁移和默认值。
8. 修改 Docker 数据目录时必须同时检查 `/app/data` 持久化。
9. 前端新增函数后检查页面初始化流程，避免一个未定义函数让整个页面停止渲染。
10. 涉及上游接口的代码尽量提供合理兜底，不要只依赖单一接口。

---

## ⚠️ 免责声明

本项目仅供个人学习、技术研究和交流使用。使用者应自行遵守当地法律法规、版权要求以及相关平台服务条款。项目作者不对因使用本项目产生的数据损失、账号风险或其他后果承担责任。

---

## 📄 License

MIT License
