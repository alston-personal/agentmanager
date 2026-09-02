# AgentOS ONE Onboarding for Antigravity executors

Use this skill for the actual executor/session running inside the Antigravity IDE surface. Built-in Gemini and built-in Codex are distinct executor identities even when they share the same IDE and ONE adapter.

## Identity fence

- `antigravity` is the IDE surface.
- Built-in Antigravity Gemini and built-in Antigravity Codex are distinct target executors.
- `agy`, standalone `gemini`, Claude, Codex CLI, and other provider processes are separate identities. Never use one as proof for another.
- The PreInvocation hook may bind executor identity only from its current `modelName`.
- The generic MCP process has no trustworthy caller-model identity and therefore remains executor-identity unbound.

## Continuation authority

Fresh-session continuation selection is owned by ONE, not by the IDE workspace.

The runtime selector is `agentos.active-continuation/v1` and contains only:

- `project_id`
- `index_id`
- `ir_id`

It is a pointer, not a second state store. The authoritative working state is still the referenced `agentos.ir/v1` Canonical IR and matching `agentos.execution-head/v1` generation.

On the first model invocation, the global Antigravity `PreInvocation` hook:

1. reads the ONE active selector;
2. resolves that project through the trusted Oracle-local ONE projection;
3. verifies selector `index_id` / `ir_id` exactly match the current canonical generation;
4. injects a bounded `source=ONE_PREINVOCATION_IR` envelope with `selection_source=ONE_ACTIVE_CONTINUATION`;
5. binds built-in Gemini/Codex identity only when `modelName` proves it.

`workspacePaths` are not continuation authority. A conversation opened in `/home/ubuntu/acas`, `agentmanager/workspace/...`, or another workspace must still receive the ONE-selected IR. Local workspace state may be used only after newer explicit user intent changes the task or AgentOS deliberately activates another canonical continuation.

## Existing implementation on this branch

Reuse these files; do not build another protocol:

- `agent_core/active_continuation.py` — active Canonical IR pointer and validation.
- `agent_core/project_continuation_index.py` — canonical generation publisher/fence.
- `agent_core/canonical_ir_handoff.py` — guarded child-generation handoff.
- `agentos_node/antigravity_one_hook.py` — PreInvocation hydration and executor identity binding.
- `agentos_node/one_mcp.py` / `one_mcp_stdio.py` — credential-isolated read-only ONE MCP adapter.
- `scripts/bootstrap_antigravity_one_oracle.sh` — immutable Oracle bootstrap, selector seed/validation, installer and hook probe.
- existing ONE `/v1/health`, `/v1/bootstrap`, `/v1/resolve` contracts.

For enrolled Windows/external clients, the client adapter discovers `%LOCALAPPDATA%\AgentOS\state\client.json` in addition to `AGENTOS_CLIENT_HOME`, `AGENTOS_CLIENT_CONFIG`, and legacy `~/.agentos/client.json`. Never print or copy its credentials into model-visible context.

## Oracle first-run / repair procedure

Run the immutable bootstrap without switching the working checkout branch:

```bash
git -C /home/ubuntu/agentmanager fetch --no-tags origin core/issue-152-executor-awareness
git -C /home/ubuntu/agentmanager show FETCH_HEAD:scripts/bootstrap_antigravity_one_oracle.sh | bash
```

Bootstrap behavior:

- seeds the first `agentos-core` IR only if both canonical head files are absent;
- seeds the active selector only if no selector exists;
- refuses partial canonical heads;
- refuses an existing stale/invalid selector rather than silently moving it;
- installs the immutable Hook/MCP runtime;
- probes the hook using `/home/ubuntu/acas` as the deliberate workspace regression case;
- requires credential isolation.

After a successful install, reload the Antigravity window.

## MCP query surface

The registered `agentos-one` MCP server exposes read-only tools:

- `one_status`
- `one_bootstrap`
- `one_capabilities`
- `one_resolve(project)`

MCP is an explicit live-query surface. It is not the fresh-session state selector and must not be used to fabricate Gemini/Codex caller identity.

## Fresh-session acceptance

In a brand-new built-in Antigravity executor conversation with no copied vendor history, send only `繼續`.

A successful first response must be consistent with the injected Canonical IR and should expose provenance sufficient to verify:

- `source=ONE_PREINVOCATION_IR`
- `selection_source=ONE_ACTIVE_CONTINUATION`
- selected `project_id`
- selected `index_id`
- selected `ir_id`
- executor class bound from PreInvocation when `modelName` proves it

The executor must not choose ACAS, if-tv-station, Zeus Writer, Pulse/PM2, or any other local state merely because that workspace is active.

For explicit validation, `one_status` / `one_resolve` may then confirm Realm/Node connectivity and current project state, but connectivity evidence is separate from executor identity evidence.

## Safety / authority

- Work only on the declared #152 worker/integration lane unless canonical Core changes ownership.
- Do not merge or push protected `main`/`master`/`release/*` without explicit human authorization.
- Do not expose or commit bearer tokens, OAuth credentials, vendor session files, or auth/config contents.
- Do not broaden permissions on Antigravity/Gemini/Codex private directories.
- Do not reconstruct continuation from local workspace state when the active selector/IR is unavailable; fail closed instead.
- Persist only sanitized evidence.

## Completion report

Report sanitized bootstrap/hook evidence, selector generation, fresh-session first response, executor identity provenance, and any blocker to #152. Cross-executor E3 is verified only after independent fresh executor sessions reproduce the same ONE-selected generation without copied vendor history.
