# 卡片扩展约定

本文定义 MovieSync 当前代码中的资源来源卡片与存储目标卡片边界，作为后续接入新平台时的实现清单。卡片注册表只管理已经由应用加载的实例；目前并不支持从管理页面下载或执行任意第三方代码。

## 资源来源卡片（`resource_source`）

实现应继承 `ResourceSourceCard`，并提供唯一、稳定的小写 `manifest.id`。核心搜索流程依赖的标准资源字段如下：

- `pwd_id`：来源资源的稳定标识，必须能交给所选存储目标解析。
- `source_id` / `source_name`：来源卡片 ID 与展示名称。
- `storage_target_id`：当资源只能由特定网盘解析时明确指定；可通用解析时可留空。
- `channel` / `channel_id`：可选的频道或来源位置，用于展示和追剧定位。

最小能力是 `search(movie, config)` 与 `check(config)`。如果卡片支持按频道扫描新内容，还应实现 `search_channel(channel, title, config)`；不支持时基类默认返回空列表，不能将其视为已支持自动追剧扫描。

返回的资源应为字典列表；单个坏结果不应破坏其他结果。异常由管理器隔离并记录。卡片配置放在 `config.cards[manifest.id].config`，启用状态由同一条卡片配置的 `enabled` 控制。

## 存储目标卡片（`storage_target`）

实现应继承 `StorageTargetCard`，并提供以下能力：

- `resolve_resource(resource)`：返回标准结果，至少包含 `files`、`token`、`error`。
- `list_files(resource)`：返回统一文件列表。
- `destination_options()`：返回可供界面选择的目录选项。
- `create_folder(name, parent_id)`：返回创建或复用后的目录 ID。
- `transfer(resource, files, target_id)`：只处理经过服务端重新解析和校验的文件。

标准文件记录至少应包含 `fid`、`file_name` 和可选的 `size`。资源来源与存储目标不是任意可互换的：`pwd_id` 必须被目标平台理解，文件 ID 与分享 Token 也必须属于同一个资源。不能因为两张卡片都已注册，就假定它们可以组合。

## 文件名与集数识别

集数识别统一使用 `moviesync/services/filename_rules.py` 中的 `parse_tv_episode()`。资源卡片可通过各自的 `magic_regex` 配置增强识别；不要在平台客户端另写一套正则，否则搜索、追剧和文件重命名可能得到不同结果。兼容旧接口应委托给共享解析器，并保留原有返回值形状。

## 接入检查清单

1. 为卡片定义唯一的 `CardManifest` 与明确的 `capabilities`。
2. 对无结果、异常、重复资源 ID、无效资源 ID 和停用卡片编写测试。
3. 若支持频道扫描，覆盖新集发现、跨季比较和空搜索回退。
4. 若支持存储操作，测试资源解析、文件字段标准化、Token 不泄露与转存白名单。
5. 通过 pytest、Ruff 和 Docker 构建后再合并到 `main`。


## 已安装资源卡片插件入口

MovieSync 支持通过 Python 包的 entry point 加载可信资源来源插件，组名为 `moviesync.resource_sources`。每个入口必须指向一个工厂函数，接收单个 `context` 字典并返回 `ResourceSourceCard` 实例。当前上下文包含 `telegram`、`config_store` 和 `logger`，插件可以按需使用这些共享服务。

例如，插件包的 `pyproject.toml` 可声明：

```toml
[project.entry-points."moviesync.resource_sources"]
example = "my_moviesync_plugin:create_card"
```

工厂函数形状：

```python
from moviesync.cards import CardManifest, ResourceSourceCard

class ExampleSource(ResourceSourceCard):
    manifest = CardManifest(
        id="example",
        name="Example",
        type="resource_source",
        capabilities=("resource.search", "resource.health_check"),
    )

    def search(self, movie, config):
        return []

    def check(self, config):
        return {"status": "healthy", "message": "ok"}

def create_card(context):
    return ExampleSource()
```

插件必须作为可信 Python 包安装并随应用启动加载。**后台不会接收或执行用户上传的 Python 文件**；动态安装/卸载插件仍未开放。安装后的卡片会进入统一注册表，并出现在 `GET /api/cards`；资源搜索、集数配置和健康检查由资源来源管理器按卡片 ID 分发。
