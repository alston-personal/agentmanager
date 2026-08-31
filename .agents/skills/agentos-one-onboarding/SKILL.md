# AgentOS ONE Onboarding for the real Antigravity Gemini

Use this skill only when the current executor is the Gemini agent/session inside the Antigravity IDE/2.0 surface for this workspace.

## Identity invariant

- `antigravity` = IDE/agent surface.
- Antigravity's built-in Gemini session = the executor this task is targeting.
- `agy` is a separate executor/provider even if it uses a Gemini-family model. **Do not use `agy` as proof that the Antigravity Gemini is connected to ONE.**
- `gemini` CLI is also a separate surface unless evidence proves the active IDE session is backed by that exact provider/session.

## Goal

Make the actual fresh Antigravity Gemini session a governed ONE-aware executor without copying vendor chat history and without giving the model Realm/node credentials.

The result must let a fresh Antigravity Gemini session:

1. discover that this workspace participates in AgentOS/ONE;
2. resolve the current project/active goal/continuation from canonical ONE state;
3. receive relevant ONE Experience hydration/provenance when available;
4. know the explicit authority/mutation boundary;
5. invoke at least one benign ONE query through a mediated adapter;
6. return a governed receipt or handoff that can be consumed by AgentOS;
7. repeat the same behavior from a new Antigravity Gemini conversation without relying on the previous vendor session.

## Existing Core contracts — reuse, do not replace

Current AgentOS already has:

- Realm `/v1/bootstrap` for node/realm/capability context;
- Realm `/v1/resolve` for project identity, active goal, continuation, node context, and mutation boundary;
- `agentos.session-bridge/v0.1` for provider/session `discover`, `snapshot`, `harvest`, `attach`, `inject`, `handoff`;
- node task/receipt transport;
- Experience hydration from #117;
- the #152 invariant that the Node is the durable Realm participant and executor hosts do not own Realm transport credentials.

Do not create a competing generic protocol unless current contracts are demonstrably insufficient.

## Preferred Antigravity integration point

Antigravity officially supports MCP servers. For Antigravity 2.0 / IDE / CLI, the user-level MCP client configuration is `~/.gemini/antigravity/mcp_config.json`.

Prefer MCP as the first provider-side integration mechanism because it reaches the actual Antigravity Agent/Gemini session rather than a sibling CLI process.

The preferred shape is:

```text
Antigravity Gemini
        |
        | logical ONE tools/resources only
        v
ONE MCP/provider adapter
        |
        | trusted Node-side mediation
        v
AgentOS ONE / canonical state
```

The Gemini model/session must never receive a raw Realm bearer credential in prompt text, MCP resource content, committed config, or model-visible environment output.

## Work order

### 1. Prove the actual local identity/surface

From inside the current Antigravity Gemini session, record sanitized evidence of:

- active workspace root;
- that this is the Antigravity IDE/2.0 Agent surface;
- available MCP configuration path(s);
- current workspace `.agents` discovery behavior;
- current repo branch and commit.

Do not dump auth/token/session files. Do not copy private Antigravity session state into the repository.

### 2. Inspect existing AgentOS primitives

Read, at minimum:

- `.agents/AGENTS.md`
- `AGENTS.md`
- `docs/CURRENT_STATE.md`
- `agent_core/realm_server.py`
- `agent_core/resolve_facade.py`
- `agentos_node/session_bridge.py`
- `agentos_node/agent_surfaces.py`
- Issue #152 context if GitHub access is available.

Confirm what is already implemented before adding code.

### 3. Build the narrow provider adapter

Prefer a small local MCP server or equivalent Antigravity-supported provider adapter that exposes only bounded logical operations such as:

- `one_status`
- `one_resolve(project)`
- `one_experience(project_or_goal)` when Experience integration is available
- `one_capabilities`
- `one_handoff(...)` / `one_receipt(...)` through a governed Node-side path

Names are not canonical yet; preserve existing Core schemas internally.

The adapter may execute on the trusted Node/ubuntu side and may use local canonical data or existing authenticated Core calls. The model-facing MCP contract must contain no Realm/node bearer credential.

### 4. Configure Antigravity MCP

When the adapter is ready, add a **secret-free** MCP server entry to `~/.gemini/antigravity/mcp_config.json` pointing to the local adapter. Prefer a local stdio/server command or localhost endpoint whose sensitive authentication remains outside model-visible content.

Do not commit personal OAuth tokens, bearer tokens, API keys, or private credential material to the repository.

### 5. Live E2 acceptance with the actual Antigravity Gemini

Start a fresh Antigravity Gemini conversation and verify it can answer from the ONE bridge, not from vendor history:

- What Realm/Node/surface am I participating through?
- What project is this workspace associated with?
- What is the current active goal / next action?
- Is mutation currently allowed? Why?
- What ONE capabilities can I call?

Then perform one benign mediated ONE query and emit one governed receipt/handoff.

Evidence must identify `surface=antigravity` and the actual IDE Gemini executor/session class. Evidence from `agy`, standalone `gemini`, Claude, or Codex does not satisfy this acceptance.

### 6. Fresh-session regression

Open a second fresh Antigravity Gemini conversation with no copied conversation history. It must rediscover ONE through workspace bootstrap/MCP and recover the same canonical project/goal/authority state within the expected freshness window.

### 7. Generalize only after first success

After the first machine passes E2, extract the minimum portable onboarding bundle for other machines:

```text
repo checkout
  -> `.agents/AGENTS.md` + onboarding skill
  -> trusted local ONE adapter install
  -> secret-free Antigravity MCP registration
  -> Node enrollment / adapter credential setup outside model context
  -> Antigravity refresh/reopen
  -> ONE discovery probe
  -> fresh-session acceptance
```

Then validate the same pattern with Antigravity Codex as a distinct executor/session. Do not assume Gemini and Codex share session identity merely because they share the Antigravity surface.

## Safety / authority fences

- Work on `core/issue-152-executor-awareness` unless canonical Core explicitly assigns another worker branch.
- Do not merge or directly push protected `main`.
- Do not chmod private vendor credential/session directories to broaden access.
- Do not copy Antigravity/Gemini/Codex credentials or vendor session files into AgentOS shared storage.
- Do not make the executor host a Realm Node just to get credentials.
- Do not use `agy` as a substitute for the Antigravity Gemini acceptance target.
- Persist only sanitized implementation/evidence artifacts.

## Completion report

Report back to #152 with:

- exact adapter/MCP files added;
- local Antigravity surface identity evidence;
- fresh Gemini E2 transcript/evidence summary (sanitized);
- whether a second fresh Gemini session rediscovered ONE;
- credentials/authority boundary used;
- what is machine-specific vs portable;
- proposed minimal onboarding recipe for a second machine;
- blockers for repeating the proof with Antigravity Codex.
