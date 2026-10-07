# Changelog

## 2.0.0

- 完成核心代码分层重构
- 统一配置、认证、订阅和日志的数据持久化
- 增加安全的 Secret Key 持久化
- Cookie 改为服务端管理，不再写入浏览器 `localStorage`
- 配置 API 不再返回真实 Cookie
- 增加 CSRF 防护和登录失败限流
- 修复自动追剧忽略 `interval_hours` 的问题
- 增加订阅任务互斥执行与 UUID 标识
- Quark 分享文件解析增加分页、递归和规模上限
- 转存增加服务端 FID 白名单验证
- Telegram 解析改用 DOM parser
- 增加图片代理 SSRF 限制
- 增加 `/healthz` 健康检查和 `/openlist` 配置跳转
- Docker 改用 Gunicorn 单 worker + threads
- CI 增加 SHA 镜像标签、Buildx 缓存与手动触发
- 新增底层单元测试
