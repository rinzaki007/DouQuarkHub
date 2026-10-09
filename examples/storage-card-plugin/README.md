# MovieSync 示例存储卡片插件

这是一个独立 Python 包，用来验证第三方存储卡片能否仅通过安装包和
`moviesync.storage_targets` entry point 接入 MovieSync，而不修改核心代码。

> **安全提示：** 本示例只演示插件发现、配置和连接检查，不连接网盘、不创建真实目录，也不转存文件。它不是可用的云盘适配器。

## 安装到 MovieSync 所在的 Python 环境

在 MovieSync 仓库根目录执行：

```bash
python -m pip install ./examples/storage-card-plugin
```

安装后重启 MovieSync。应用启动时会自动发现入口并加载卡片。打开后台「卡片管理」后，应能看到 **示例存储（仅演示）**，然后可以进入配置并填写显示名称。

Docker 部署时，插件必须安装到运行 MovieSync 的同一个镜像/ Python 环境中。可在自定义镜像构建阶段安装，例如：

```dockerfile
COPY examples/storage-card-plugin /tmp/moviesync-example-storage-card
RUN python -m pip install /tmp/moviesync-example-storage-card \
    && rm -rf /tmp/moviesync-example-storage-card
```

不要把不可信插件安装到生产实例。Python 插件拥有与 MovieSync 进程相同的系统权限；当前版本不会在后台动态安装、卸载或热重载插件。

## 如何扩展为真实存储卡片

1. 将 `pyproject.toml` 中的入口组保持为 `moviesync.storage_targets`。
2. 工厂函数接收一个 `context` 字典并返回 `StorageTargetCard` 实例。
3. 使用唯一、稳定的小写 `manifest.id`，并通过 `config_fields` 声明后台配置。
4. 实现资源解析、文件列表、目标目录和转存方法；必须校验分享 ID、文件 ID、Token 及目标目录。
5. 对凭据字段设置 `secret: true`，不要把 Cookie、Token 或密码写入日志。
6. 在真实调用之前确认卡片启用状态，并覆盖错误、超时、重复任务和敏感信息测试。

完整接口约定见仓库根目录的 [CARD_CONTRACT.md](../../CARD_CONTRACT.md)。
