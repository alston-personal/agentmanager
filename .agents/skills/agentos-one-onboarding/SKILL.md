# AgentOS ONE Onboarding for the real Antigravity Gemini

Use this skill only for the Gemini agent/session actually running inside the Antigravity IDE for this workspace.

## Identity fence

- `antigravity` is the IDE surface.
- Antigravity built-in Gemini is the target executor.
- `agy`, standalone `gemini`, Claude and Codex are separate executor/session identities. Never use them as proof that this Gemini is connected to ONE.

## Goal

A fresh Antigravity Gemini conversation must rediscover AgentOS ONE from workspace bootstrap, query canonical Realm/project/goal/authority state, and do so without receiving the raw Realm/node bearer token in model-visible MCP results or config.

## Existing implementation on this branch

Reuse these files; do not build another protocol:

- `.agents/AGENTS.md` — Antigravity startup/bootstrap instruction.
- `agentos_node/one_mcp.py` — credential-isolated read-only ONE MCP adapter.
- `scripts/install_antigravity_one_mcp.py` — installs MCP SDK in AgentOS client state, probes ONE, and registers the `agentos-one` stdio server in Antigravity's MCP config.
- existing ONE `/v1/health`, `/v1/bootstrap`, `/v1/resolve` contracts.

The adapter discovers the existing AgentOS client config. On Windows it supports `%LOCALAPPDATA%\AgentOS\state\client.json` in addition to `AGENTOS_CLIENT_HOME` / `AGENTOS_CLIENT_CONFIG` and legacy `~/.agentos/client.json`.

## First-run procedure

From the repository root on `core/issue-152-executor-awareness`:

```bash
python scripts/install_antigravity_one_mcp.py --repo .
```

Do not print or copy `client.json` contents. The installer may read it locally; the token must stay inside the MCP process boundary.

A successful installer result must show:

- `ok: true`
- `server: agentos-one`
- `credential_in_mcp_config: false`
- `probe.probe: PASS`
- `refresh_required: true`

If the ONE probe fails, stop and diagnose the existing AgentOS client/ONE route. Do not silently rewrite `one_url`, credentials, vendor session files, firewall, or protected branches.

## Antigravity activation

After installation, refresh MCP servers in Antigravity (Agent panel `...` -> MCP Servers / Manage MCP Servers -> refresh), or reload the Antigravity window.

The registered `agentos-one` MCP server exposes only these read-only tools in this first slice:

- `one_status`
- `one_bootstrap`
- `one_capabilities`
- `one_resolve(project)`

Do not claim receipt/handoff write support yet; that belongs to the next governed #152 slice.

## E2 live acceptance

In a fresh Antigravity Gemini conversation with no copied vendor history:

1. call `one_status` and confirm `connected=true`, `surface=antigravity`, correct Realm/Node, and `credential_exposed=false`;
2. call `one_capabilities`;
3. resolve the current AgentOS project with `one_resolve(...)` using the canonical project name/alias available from the workspace/ONE state;
4. report the returned `active_goal`, `next_action`, and `mutation_allowed` exactly from ONE, not from memory;
5. identify yourself as the Antigravity Gemini executor, not `agy`.

The first test proves read-only ONE awareness. It does not yet prove Experience uplift, receipt/handoff writes, or cross-executor continuity.

## Fresh-session regression

Open a second brand-new Antigravity Gemini conversation. Without copying the first chat, it must rediscover `.agents/AGENTS.md`, the `agentos-one` MCP server, and the same canonical Realm/project/goal/authority state.

## Safety / authority

- Work only on `core/issue-152-executor-awareness` unless canonical Core changes ownership.
- Do not merge or push protected `main`.
- Do not expose or commit bearer tokens, OAuth credentials, vendor session files, or auth/config contents.
- Do not broaden permissions on Antigravity/Gemini/Codex private directories.
- Do not substitute `agy` for the IDE Gemini acceptance target.
- Persist only sanitized evidence.

## Completion report

Report to #152: installer result (sanitized), MCP config location, `one_status` result, project resolve result, fresh-session result, and any blocker. Then Core can extract the portable onboarding recipe for another machine and repeat with Antigravity Codex as a distinct executor.