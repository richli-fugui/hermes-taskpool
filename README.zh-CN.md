# Hermes Task Pool

[English](README.md) | [简体中文](README.zh-CN.md)

面向 Hermes Desktop 与 Hermes Agent 的项目级任务池。桌面面板和 Agent 工具共用当前 Hermes profile 中的存储。任务卡只记录进度，不会分派任务或自动启动工作。

## 安装

**推荐：在 Hermes Desktop 中同时安装两个组件**

[在 Hermes Desktop 中从 Git 安装](hermes://plugin/install?repo=richli-fugui/hermes-taskpool&enable=1)

1. 打开上方安装链接，或进入 **Capabilities → Plugins → Install from Git**。
2. 检查仓库内容，并同时选择 **Agent plugin** 和 **Desktop plugin**。
3. 确认安装。如果桌面组件尚未启用，在插件管理器中启用 `pp-pane`。
4. 确认 Agent 使用的 surface 已启用 `project_task_pool`，并在已登记的 Hermes 项目中启动新对话。

远程 Gateway 场景下，Agent 后端必须安装在运行 Gateway 的 Hermes 环境；桌面界面组件则必须安装到运行 Hermes Desktop 的设备。

**仅安装 Agent/CLI 组件：**

```sh
hermes plugins install richli-fugui/hermes-taskpool --enable
hermes plugins doctor pp-pane --ci
hermes tools enable project_task_pool --platform cli
```

以上命令安装并启用 Agent 后端及 CLI 工具集。要使用桌面面板，还需在运行 Hermes Desktop 的设备上，通过 **Install from Git** 安装桌面组件。

完整安装、验证和故障排查：[简体中文](docs/INSTALL.zh-CN.md) | [English](docs/INSTALL.md)。

## 功能

- Hermes Desktop 任务池面板，包含五种状态：`todo`、`doing`、`blocked`、`review` 和 `done`。
- Agent 工具：`task_pool_list`、`task_pool_add` 和 `task_pool_update`。
- 按 Hermes 项目隔离：Agent 根据当前会话工作目录和 Hermes 已登记的项目解析身份；项目未登记或身份不明确时会拒绝写入。
- 安全写入：新增任务支持幂等请求键；更新必须提供当前任务 revision。Agent API 不提供删除操作。
- 桌面面板与 Agent 共用 Hermes 管理的 SQLite 存储，无需单独部署数据库服务或 API key。

工具是否可用取决于当前 Agent surface 的工具集设置及会话创建时的工具快照。如果会话找不到 `task_pool_list`，请检查插件和 `project_task_pool` 是否启用，然后新建对话或执行 `/reset`。桌面面板可见并不能证明当前 Agent 会话已经获得这些工具。

自定义 Git 来源不是经过 Hermes 官方目录审核的插件。安装前请审阅代码；Hermes Desktop 插件在应用权限下运行，并非沙箱隔离。

## 数据与兼容性

- 任务按 Hermes 项目 ID 隔离，存放在当前 profile/Gateway 中。同一 Gateway 和 profile 下的客户端共用数据；不同 profile 或 Gateway 使用不同存储。
- 桌面组件首次打开项目时，会一次性导入有效的旧版 `board.v1.*` 卡片，并保留原始本地数据。这不是持续的跨设备同步。
- 项目路径解析目前使用 Hermes 内部 API `hermes_cli.projects_db.project_for_path`。本项目已在 Hermes Agent `v0.22.2+2579.g601491f`（`2026.9.24`）上验证。该 API 不属于公开兼容性承诺；升级 Hermes 后应重新运行插件验证和项目级只读测试。
- 发布包不含账号凭据、私人部署设置、本地任务数据库或安装证据，也不依赖外部服务。

## 构建与测试

运行测试需要 Node.js、Python，以及用于后端集成测试的 Hermes Python 环境。

```sh
npm ci
npm run build
npm test
npm run check
```

`src/plugin.js` 和 `src/agent_plugin/` 是规范源码。`npm run build` 会更新仓库根目录下供 Git 安装使用的统一插件文件，并将可选构建产物写入被忽略的 `dist/`。发布包测试会检查根目录副本与规范源码是否一致。

## 许可证

本项目采用 [MIT License](LICENSE)。
