# 安装与验证 Hermes Task Pool

[English](INSTALL.md) | [简体中文](INSTALL.zh-CN.md)

本项目是一个统一的 Hermes 插件：Agent 后端与 Hermes Desktop 界面从同一个 Git 仓库安装。仓库根目录就是插件包，普通安装不需要先运行 Node 构建。

这是自定义 Git 来源，不是经过官方目录审核的插件。安装前请审阅代码。Hermes Desktop 插件在应用权限下运行，并非沙箱隔离。

## 环境要求

- 支持原生 Git 插件安装器和插件 API 的 Hermes Agent。
- 支持桌面插件及 **Install from Git** 的 Hermes Desktop 版本。
- 项目目录必须已登记在 Hermes Projects 中。当前会话目录无法映射到已登记项目时，Agent 工具会拒绝写入。

本项目已在 Hermes Agent `v0.22.2+2579.g601491f`（`2026.9.24`）上验证。这是已验证版本，不代表所有更早版本都兼容。项目解析器使用内部 API `hermes_cli.projects_db.project_for_path`；升级 Hermes 后应重新进行兼容性验证。

## 推荐：在 Hermes Desktop 中安装两个组件

1. 打开 [Hermes Desktop Git 插件安装器](hermes://plugin/install?repo=richli-fugui/hermes-taskpool&enable=1)，或进入 **Capabilities → Plugins → Install from Git**。
2. 如页面要求，输入 `richli-fugui/hermes-taskpool`。
3. 检查仓库内容，并选择 **Agent plugin** 与 **Desktop plugin**。
4. 确认安装。如果界面组件仍处于关闭状态，在 Desktop 插件管理器中启用 `pp-pane`。
5. 确认 Agent 插件已在当前 Hermes profile 中启用。此插件提供的工具集名为 `project_task_pool`。
6. 在需要使用工具的 Agent surface 上启用该工具集。CLI 示例：`hermes tools enable project_task_pool --platform cli`。其他 surface 可使用 `hermes tools` 交互界面，或将 `cli` 替换为对应 platform 名称。
7. 在已登记的 Hermes 项目中启动新对话，或对现有对话执行 `/reset`，然后确认该会话可以发现 `task_pool_list` 并返回预期项目。

桌面面板可见并不代表某个 Agent 会话已获得这些工具。工具是否可用取决于当前 surface、profile、Gateway 以及会话工具快照。

## 仅安装 Agent/CLI，或使用远程 Gateway

在运行 Hermes Agent/Gateway 的机器上安装 Agent 后端：

```sh
hermes plugins install richli-fugui/hermes-taskpool --enable
hermes plugins doctor pp-pane --ci
```

随后为目标 surface 启用 `project_task_pool`。CLI 可运行：

```sh
hermes tools enable project_task_pool --platform cli
```

其他 surface 可替换为其 platform 名称，或使用交互式 `hermes tools` 命令。然后启动新对话。若还要安装桌面界面，请在运行 Hermes Desktop 的机器上使用 **Install from Git**。远程 Desktop 客户端和 Gateway 是不同的安装目标：后端需安装在提供 Agent 工具的 Gateway/profile 上，桌面界面文件则需安装在 Desktop 客户端。

如需固定到已审核的不可变版本，可在 `--ref` 后指定 40 位 Git commit SHA：

```sh
hermes plugins install richli-fugui/hermes-taskpool --ref <40-character-commit-sha> --enable
```

## 验证安装

在 Hermes Agent/Gateway 环境中运行：

```sh
hermes plugins list
hermes plugins doctor pp-pane --ci
hermes tools list
```

确认 `pp-pane` 已启用，并确认目标 platform 已启用 `project_task_pool`。随后在一个新建的项目会话中验证 `task_pool_list` 确实可用。插件 Doctor 只检查插件注册状态，不代表已创建的旧会话已加载该工具集。

在已登记的项目中，预期行为如下：

- `task_pool_list` 读取当前项目的任务池。
- `task_pool_add` 在同一个 profile-backed store 中新建任务卡。
- `task_pool_update` 要求提供任务卡当前 revision。
- 未登记或身份不明确的项目会被拒绝，不会自动猜测项目。

## 数据行为

- 存储由 Hermes 插件存储管理，并按当前 profile/Gateway 和已登记项目 ID 隔离。无需单独部署数据库服务、API key 或云账户。
- 只有连接到同一 Gateway 和 Hermes profile 的 Desktop 与 Agent 客户端才会共用数据。
- Desktop 插件首次打开项目时，会验证并一次性导入该设备上的旧版 `board.v1.*` 卡片，同时保留原始卡片。如导入卡片与共享存储中的卡片 ID 冲突，会保留共享存储中的卡片，并保留冲突副本供后续检查。这是一次性迁移，不是持续同步。
- Agent API 提供读取、新增和更新工具，不提供删除、指派或派发；新增卡片不会启动任务。

## 故障排查

### Agent 找不到 `task_pool_list`

1. 检查 `pp-pane` 是否已安装并启用：`hermes plugins list`。
2. 检查插件注册：`hermes plugins doctor pp-pane --ci`。
3. 检查当前 surface 的工具集设置。CLI 可运行 `hermes tools enable project_task_pool --platform cli`；其他 surface 可通过 `hermes tools` 选择，或指定对应的 `--platform`。
4. 启动新对话或执行 `/reset`；工具列表会绑定在会话快照中。
5. 确认当前会话使用的是预期 Hermes profile/Gateway。另一个 profile 或 surface 上的 CLI 成功，不代表当前会话也能使用。

### 工具返回“项目身份未确认，拒绝写入”

当前会话工作目录无法映射到有效的已登记 Hermes 项目。失败调用会附带机器可读的 `code` 和 `hint`（例如 `PROJECT_IDENTITY_UNCONFIRMED`、`REVISION_CONFLICT`），按提示处理即可。请在 Hermes 中登记或修正该项目，然后从登记路径下启动会话。不要通过传入项目 ID 或路径绕过限制；工具刻意不接受这些参数。

### Desktop 面板未显示

确认安装 Git 插件时选择了 Desktop 组件，并在插件管理器中启用了 `pp-pane`。Desktop 组件默认可选启用。如果新插件未加载，可运行 Hermes 的 **Reload desktop plugins** 命令，并查看应用显示的加载错误。

### 插件验证提示使用了 Hermes 内部 API

当前实现使用 Hermes 内部项目数据库解析器，以防止跨项目写入。对于已验证版本，这是已知兼容性提示，但未来版本可能改变该接口。升级 Hermes 后，重新运行 `hermes plugins validate <plugin-directory> --json`、插件 Doctor，以及一个针对已登记项目的只读验证。

## 开发检查

规范源码为 `src/plugin.js` 和 `src/agent_plugin/`。仓库根目录中的 `plugin.yaml`、Python 文件、`dashboard/` 与 `desktop/` 是安装用镜像；修改源码后需要重新生成：

```sh
npm ci
npm run build
npm test
npm run check
```

发布包测试会检查可通过 Git 安装的根目录镜像与规范源码完全一致。安装不需要 `dist/`、测试缓存、本地证据或历史归档。

## 许可证

本项目采用 [MIT License](../LICENSE)。
