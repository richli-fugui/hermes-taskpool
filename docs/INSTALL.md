# Install and verify Hermes Task Pool

This project is a unified Hermes plugin: the Agent/backend half and the Hermes Desktop UI are installed from the same Git repository. The repository root is the plugin package; no Node build is needed for ordinary installation.

This is a custom Git source, not a reviewed catalog entry. Review the source before installing. Hermes Desktop plugins run inside the app with the app's authority; they are not sandboxed.

## Requirements

- A Hermes Agent installation with the native Git plugin installer and plugin APIs.
- A Hermes Desktop build that supports Desktop plugins and **Install from Git**.
- The project directory must be registered in Hermes Projects. Agent tools fail closed when the current session directory cannot be mapped to a registered project.

Validated on Hermes Agent `v0.22.2+2579.g601491f` (`2026.9.24`). This is a tested version, not a promise that every earlier version is compatible. The project resolver uses the internal `hermes_cli.projects_db.project_for_path` API; Hermes upgrades should be treated as a compatibility check.

## Recommended: install both components in Hermes Desktop

1. Open the [Hermes Desktop Git plugin installer](hermes://plugin/install?repo=richli-fugui/hermes-taskpool&enable=1), or open **Capabilities → Plugins → Install from Git**.
2. Enter `richli-fugui/hermes-taskpool` if asked for the repository.
3. Review the repository and select both **Agent plugin** and **Desktop plugin**.
4. Confirm the install. Enable the `pp-pane` Desktop plugin in the Desktop plugin manager if the UI component remains off.
5. Confirm the Agent plugin is enabled for the active Hermes profile. The supplied toolset is named `project_task_pool`.
6. Enable the toolset on the Agent surface you use. For the CLI, run `hermes tools enable project_task_pool --platform cli`. For another surface, use `hermes tools` or the same command with that surface's platform name.
7. Start a new conversation (or `/reset` an existing one) inside a registered Hermes project. Ask: **“整理一下任务卡”**.

A visual panel does not prove that an Agent session has the tools. In that new conversation, verify that `task_pool_list` is discoverable and that its result reports the expected registered project. Tool availability is specific to the current surface, profile, Gateway, and session snapshot.

## Agent/CLI-only or remote Gateway install

On the machine running the Hermes Agent/Gateway, install the Agent/backend half with:

```sh
hermes plugins install richli-fugui/hermes-taskpool --enable
hermes plugins doctor pp-pane --ci
```

Then enable the toolset for the surface you use. For CLI, run `hermes tools enable project_task_pool --platform cli`; for another surface, substitute its platform name or use the interactive `hermes tools` command. Start a new conversation. To install the Desktop half, use the Hermes Desktop **Install from Git** flow on the machine running the Desktop app. A remote Desktop client and Gateway are separate install targets: the backend must be available to the Gateway/profile that serves tools, and the UI file must be available to the Desktop client.

For a reproducible install pinned to a reviewed immutable commit, pass the 40-character Git commit SHA with `--ref`:

```sh
hermes plugins install richli-fugui/hermes-taskpool --ref <40-character-commit-sha> --enable
```

## Verify the installation

Run these on the Hermes Agent/Gateway installation:

```sh
hermes plugins list
hermes plugins doctor pp-pane --ci
hermes tools list
```

Confirm `pp-pane` is enabled and the `project_task_pool` toolset is enabled on the intended platform. Then use a fresh project conversation to verify `task_pool_list` is actually available. A successful plugin doctor checks registration; it does not prove that a previously created conversation received the tool.

Expected behavior in a registered project:

- `task_pool_list` reads that project's board.
- `task_pool_add` creates cards in the same profile-backed store.
- `task_pool_update` requires the card's current revision.
- An unregistered or ambiguous project identity is rejected rather than guessed.

## Data behavior

- The store is owned by Hermes plugin storage and scoped to the active profile/Gateway and registered project ID. No separate database service, API key, or cloud account is required.
- Desktop and Agent clients share data only when they use the same Gateway and Hermes profile.
- When the Desktop plugin first opens a project, it validates and imports that device's legacy `board.v1.*` cards once. It retains the original local cards. If an imported card conflicts with an existing card ID, the shared card is kept and the conflicting copy is retained for later review. This is a one-time migration, not continuous device sync.
- The Agent API exposes list, add, and update tools; it does not expose card deletion, assignment, or dispatch. Adding a card does not start work.

## Troubleshooting

### The Agent cannot find `task_pool_list`

1. Check that `pp-pane` is installed and enabled: `hermes plugins list`.
2. Check registration: `hermes plugins doctor pp-pane --ci`.
3. Check the active surface's tool selection. For CLI, run `hermes tools enable project_task_pool --platform cli`; otherwise select the toolset with `hermes tools` or pass the correct `--platform` value.
4. Start a new conversation or run `/reset`; tool lists are bound to a session snapshot.
5. Verify the conversation is using the intended Hermes profile/Gateway. A CLI success on another profile or surface is not proof for this conversation.

### The tool returns “项目身份未确认，拒绝写入”

The session working directory is not resolving to an active registered Hermes project. Register or correct the project in Hermes, then start a session whose working directory is inside that project's registered path. Do not pass a project ID or path as a workaround; the tools intentionally do not accept either.

### Desktop panel is missing

Confirm that the Desktop half was selected during Git installation and that `pp-pane` is enabled in the Desktop plugin manager. The Desktop component is opt-in. If the app does not load a newly installed plugin, use its **Reload desktop plugins** command and inspect any load error shown by Hermes.

### Plugin validation warns about an internal Hermes API

The current implementation uses Hermes's internal project database resolver to prevent cross-project writes. The warning is expected for this version, but it means an upgrade can change that interface. Re-run `hermes plugins validate <plugin-directory> --json`, the plugin doctor, and a fresh registered-project read-only smoke test after upgrading Hermes.

## Development checks

The canonical source files are `src/plugin.js` and `src/agent_plugin/`. The root `plugin.yaml`, Python files, `dashboard/`, and `desktop/` are generated install mirrors; regenerate them after source changes:

```sh
npm ci
npm run build
npm test
npm run check
```

The package test checks that the Git-installable root mirrors exactly match the canonical sources. `dist/`, test caches, local evidence, and historical archives are not required for installation.
