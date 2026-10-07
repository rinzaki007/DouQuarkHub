# MovieSync 2.x 架构说明

## 目标

2.x 保留原有产品能力，但把 Web、业务、第三方平台、调度和持久化彻底解耦。

```text
Browser
  │
  ▼
Flask Web / Blueprints
  │
  ├── Auth / CSRF / Rate Limit
  ├── Config API
  ├── Movie API
  ├── Search API
  ├── Transfer API
  └── Subscription API
        │
        ▼
     Services
        │
        ├── SearchService
        └── SubscriptionManager
        │
        ▼
     Providers / Clients
        ├── DoubanClient
        ├── TelegramClient
        └── QuarkClient
        │
        ▼
     HTTP + local JSON storage
```

## 目录

```text
moviesync/
├── app.py                 # Application Factory 与依赖组装
├── settings.py            # 环境变量、数据目录、Secret Key
├── storage.py             # 原子 JSON 持久化与线程锁
├── config_store.py        # 应用配置与频道配置
├── auth.py                # 管理员初始化、密码校验
├── logging_setup.py       # RingBuffer + 文件轮转日志
├── clients/
│   ├── http.py            # 线程本地 Session、重试、JSON 错误处理
│   ├── douban.py          # 豆瓣适配
│   ├── telegram.py        # Telegram HTML 解析与频道探测
│   └── quark.py           # 夸克 API 适配
├── services/
│   ├── search.py          # 频道并发检索、候选聚合、转存校验
│   └── subscriptions.py  # 订阅 CRUD、执行、调度
└── web/
    ├── __init__.py        # Web 中间件、认证保护、错误处理
    └── routes.py          # 页面及 API 路由
```

## 关键设计

### 1. 所有运行数据统一进入 `/app/data`

管理员、Cookie、配置、订阅、Secret Key 和日志都由数据目录管理。这样 Docker 只需要挂载一个 volume 即可完整持久化。

### 2. Secret 与 Cookie 不再暴露给浏览器

配置接口只返回 `has_quark_cookie`。前端不再通过 `localStorage` 保存 Cookie；真正执行搜索、转存和追剧时由服务端读取配置。

### 3. 转存时不信任客户端的 Token

搜索结果返回给浏览器的候选信息不包含 `stoken`。用户确认转存后，服务端重新解析分享链接并验证所选 FID 是否属于当前分享源，然后才执行转存。

### 4. 订阅调度真正使用 `interval_hours`

旧版本固定每小时检查一次，实际上忽略了每个任务自己的频率。2.x 为每个任务维护 `next_run_at`，调度循环每 30 秒扫描一次，到期后才执行。

### 5. JSON 存储做了原子写入

先写临时文件并 `fsync`，再 `os.replace`。避免容器异常退出时留下半截 JSON。

## 扩展方向

当前版本仍然适合单机、单实例部署。若以后出现多实例、高并发或大量订阅，可以把 `storage.py` 替换成 SQLite/PostgreSQL，把后台任务迁移到 Redis Queue/Celery，而 Web API 基本不需要改变。
