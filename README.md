# 🎬 MovieSync

> 豆瓣影视 → Telegram 资源 → 夸克网盘 → 自动转存 / 自动追剧

MovieSync 是一个简单的影视资源整理工具，主要用于：

- 🎬 浏览和搜索豆瓣电影、电视剧、综艺、动漫
- 🔎 从 Telegram 频道搜索对应影视资源
- ☁️ 解析夸克网盘分享并选择需要的文件
- 📁 将资源转存到指定的夸克目录
- ❤️ 设置自动追剧，发现新资源后自动转存
- ⚙️ 在后台管理夸克、Telegram、FID 和其他配置

---

## 📁 目录结构

```text
MovieSync/
├── moviesync/                 # Python 后端
│   ├── clients/              # 豆瓣 / 夸克 / Telegram / HTTP
│   ├── services/              # 搜索、转存、自动追剧
│   ├── web/                   # Flask 页面和 API
│   ├── app.py                # 应用初始化
│   ├── auth.py               # 管理员登录和账号安全
│   ├── config_store.py       # 配置管理
│   ├── logging_setup.py      # 日志
│   ├── settings.py           # 运行设置
│   └── storage.py            # 数据保存
│
├── static/                    # CSS / JavaScript
├── templates/                 # 网页模板
├── tests/                     # 测试文件
├── Dockerfile                 # Docker 镜像
├── main.py                    # 程序入口
├── requirements.txt           # 运行依赖
└── README.md                  # 项目说明
```

---

## 🐳 Docker 部署

### 方法一：Docker Compose

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

然后运行：

```bash
docker compose up -d
```

浏览器访问：

```text
http://你的服务器IP:8099
```

第一次打开时会进入管理员初始化页面。

### 方法二：直接使用 Docker 命令

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

如果你使用 iStoreOS，也可以把数据目录挂载到例如：

```text
/mnt/sata1-1/moviesync -> /app/data
```

这样删除或更新容器后，账号、配置和自动追剧任务仍然会保留。

---

## ⚙️ 初次使用

第一次打开 MovieSync 后：

1. 创建管理员账号
2. 登录后台
3. 填写夸克 Cookie
4. 设置默认 FID / 分类 FID
5. 添加 Telegram 资源频道
6. 返回首页搜索影视资源
7. 选择资源文件并转存到夸克

如果要使用自动追剧，在资源页面或后台创建对应的追剧任务即可。

---

## 💾 数据保存位置

MovieSync 的运行数据都会保存在 `/app/data`：

```text
/app/data/
├── auth.json             # 管理员账号
├── config.json           # MovieSync 配置
├── subscriptions.json    # 自动追剧任务
├── .secret_key           # Session 密钥
└── logs/                 # 日志
```

这些文件属于运行数据，**不要提交到 GitHub**。

---

## 🔧 常用 Docker 命令

查看运行状态：

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

更新镜像后重新创建：

```bash
docker pull ghcr.io/rinzaki007/moviesync:latest
docker stop MovieSync
docker rm MovieSync
```

然后按照上面的 Docker 命令重新创建即可。

**只要 `/app/data` 的挂载没有改变，更新容器不会丢失数据。**

---

## ⚠️ 免责声明

本项目仅供个人学习、技术研究和交流使用。

请使用者自行遵守当地法律法规、版权要求以及豆瓣、Telegram、夸克等相关平台的服务条款。

本项目不提供任何影视资源，仅提供资源搜索、整理和个人网盘转存等功能。

因使用本项目产生的账号风险、数据损失、版权问题或其他任何后果，由使用者自行承担。

---

## 📄 License

MIT License
