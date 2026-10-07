# MovieSync 重构清单

## 已完成

| 原问题 | 处理方式 |
|---|---|
| `main.py` 同时负责所有业务 | 拆成 Application / Web / Service / Client / Storage 层 |
| Cookie 同时存服务端 + `localStorage` | 改为服务端唯一可信源 |
| `/api/config` 返回完整 Cookie | 改为脱敏公共配置 |
| 认证/配置文件写在项目根目录 | 统一迁移到 `data/` |
| Docker 只挂载 `/app/data` 导致配置丢失 | 全部运行态数据进入 `/app/data` |
| `interval_hours` 不生效 | 增加 `next_run_at` 按任务调度 |
| 订阅调度与手动执行可能竞态 | 增加运行中任务集合与锁 |
| 订阅 ID 可能同秒碰撞 | 改为 UUID |
| JSON 文件直接覆盖写入 | 原子写入 |
| 大量 `print()` | 统一 Python logging + 文件轮转 + Web RingBuffer |
| 大量 `except Exception: pass` | 关键路径统一错误处理与日志 |
| Telegram HTML 使用脆弱正则解析 | 使用 BeautifulSoup DOM 解析 |
| Quark 请求没有复用连接 | 线程本地 `requests.Session` |
| Quark 分享目录只拉第一页 | 增加分页、递归深度和文件数量上限 |
| Quark 目录查找没有检查目录类型 | 仅命中目录项 |
| 转存信任浏览器传入的 `stoken/fid` | 服务端重新取 token + FID 白名单校验 |
| `/api/proxy-img` 可代理任意 URL | 仅允许 HTTPS + `doubanio.com` |
| 登录没有失败频率限制 | 增加 IP 级登录限流 |
| 状态修改接口没有 CSRF | Session CSRF Token + `X-CSRF-Token` |
| `/openlist` 没有路由 | 增加配置驱动重定向 |
| 前端存在内联 JSON 注入风险 | 候选弹窗改为索引状态引用 |
| `admin.js` 没有被后台页面加载且存在重复逻辑 | 删除重复文件 |
| 部分输入没有约束 | 对 FID、频道 ID、URL、请求体大小做校验 |
| Docker 镜像/启动方式偏开发化 | Python 3.12 + Gunicorn 单 worker + healthcheck |
| CI 只有 `latest` 标签 | 增加 SHA 标签与 Buildx 缓存 |

## 兼容策略

旧的顶层模块没有直接删除，而是保留为轻量兼容适配层：

- `quark_engine.py`
- `search_service.py`
- `subscription_manager.py`
- `utils.py`

真正的新实现都位于 `moviesync/`。

## 暂未改变

- 豆瓣及夸克上游接口地址与业务语义
- 现有 HTML UI 的主要交互方式
- 频道配置格式的主要字段
- Docker Compose 的 `8099:5000` 使用方式

这样可以尽量降低升级成本。
