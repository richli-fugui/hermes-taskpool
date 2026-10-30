# Hermes Task Pool

[English](README.md) | [简体中文](README.zh-CN.md)

A project-scoped task pool for Hermes Desktop and Hermes Agent. The Desktop panel and Agent tools share the same profile-backed store. Cards record progress only: they do not assign, dispatch, or start work.

## Install

**Recommended — install both halves from Hermes Desktop:**

[Install from Git in Hermes Desktop](hermes://plugin/install?repo=richli-fugui/hermes-taskpool&enable=1)

1. Open the link above, or open **Capabilities → Plugins → Install from Git**.
2. Review the repository and select both the **Agent plugin** and the **Desktop plugin**.
3. Confirm the install. Enable `pp-pane` in the Desktop plugin manager if the UI component is off.
4. Ensure `project_task_pool` is enabled on the Agent surface you use, then open a **new** conversation in a registered Hermes project.

The Desktop installer keeps the two components together while installing the Agent backend to the selected Hermes profile and the UI component to the Desktop app. For a remote Gateway, the backend must be installed on the Gateway's Hermes runtime; the Desktop component must be available to the machine running Hermes Desktop.

For an Agent/CLI-only installation on a machine that already runs Hermes:

```sh
hermes plugins install richli-fugui/hermes-taskpool --enable
hermes plugins doctor pp-pane --ci
hermes tools enable project_task_pool --platform cli
```

This installs the Agent/backend half. Use Hermes Desktop's **Install from Git** flow to install the Desktop half as well.

Full setup and troubleshooting: [English](docs/INSTALL.md) | [简体中文](docs/INSTALL.zh-CN.md).

## What it provides

- A Hermes Desktop task-pool panel with five states: `todo`, `doing`, `blocked`, `review`, and `done`.
- Agent tools: `task_pool_list`, `task_pool_add`, and `task_pool_update`.
- Project isolation: the Agent derives project identity from its current session working directory and Hermes's registered project list. Unregistered or ambiguous identities fail closed.
- Safer writes: `task_pool_add` supports idempotency keys; updates require the current task revision; read-after-write verification is recommended. The Agent API does not expose deletion.
- A shared SQLite-backed store managed through Hermes plugin storage; no separate database service or API key is required.

Tool availability depends on the Agent surface's enabled toolsets and the session's tool snapshot. If a conversation cannot find `task_pool_list`, check the plugin and `project_task_pool` toolset, then start a new conversation or `/reset`. Installation or a visible Desktop panel alone does not prove that a particular Agent session has the tools.

Custom Git installs are unreviewed community sources. Review the code before installing; Hermes Desktop plugins run inside the app with the app's authority and are not sandboxed.

## Card granularity

Cards work best as minimal next actions. When adding cards, the Agent tool guidance asks for: one card = one completable step; a concrete action in the title; acceptance criteria in notes; and splitting any card that needs multiple steps, sessions, or people into separate cards. This follows the GTD "next physical action" convention and the small-batch practice used in LLM agent planning research (e.g. least-to-most decomposition), where finer, independently verifiable units are easier to start, finish, and verify.

## Error payloads

Failed tool calls return structured JSON with a machine-readable `code` and a `hint` describing the supported repair, for example `PROJECT_IDENTITY_UNCONFIRMED` (register the project, restart inside its path), `REVISION_CONFLICT` (re-list, retry with the current revision), `TASK_NOT_FOUND`, `IDEMPOTENCY_CONFLICT`, and `VALIDATION_ERROR`. Nothing is written on a rejected call.

## Out of scope

This plugin deliberately does not: dispatch or start work from cards; delete cards; keep a Kanban or todo-list replacement; or sync devices continuously (legacy import is one-time). Features beyond that list are intentionally excluded to keep the pool a simple progress ledger.

## Data and compatibility

- Tasks are scoped by Hermes project ID and stored in the active Hermes profile/Gateway. Clients connected to the same Gateway and profile share data; different profiles or Gateways have separate stores.
- The Desktop component imports valid legacy `board.v1.*` cards once when opening a project. It preserves the original local data; this is a one-time migration, not ongoing device-to-device synchronization.
- Project-path resolution currently uses Hermes's internal `hermes_cli.projects_db.project_for_path` API. This implementation was validated against Hermes Agent `v0.22.2+2579.g601491f` (`2026.9.24`). The API is not a public compatibility guarantee: rerun plugin validation and a project-scoped smoke test after Hermes upgrades.
- The package contains no account credentials, private deployment settings, local task database, or installation evidence. It does not require an external service.

## Build and test

Requires Node.js, Python, and the Hermes Python runtime for the backend integration tests.

```sh
npm ci
npm run build
npm test
npm run check
```

`src/plugin.js` and `src/agent_plugin/` are the canonical sources. `npm run build` refreshes the unified plugin mirrors at the repository root for direct Git installation and writes optional local build artifacts to the ignored `dist/` directory. The release-package test verifies the mirrors match the sources.

## License

This project is licensed under the [MIT License](LICENSE).
