# AgentOS — agentmanager Project Context

This repository is the **AgentOS logic/runtime root**. Mutable project state belongs in the configured data layer; runtime semantics, contracts, tests, governance, and automation live here.

## Required reading order

Before architecture or system-level changes:

1. `README.md` — current product goal and public architecture.
2. `docs/CURRENT_STATE.md` — canonical map of **Implemented / Verified / Research** capabilities.
3. `docs/AGENTOS_NODE.md` — responsibility/resource discovery contract for cross-project work.
4. `.agent/CONSTITUTION.yaml` and relevant governance/role sources when authority or policy is involved.

Do not rely on older memory/pulse-era documents as current architecture if they disagree with `docs/CURRENT_STATE.md` and executable evidence.

## Antigravity ONE self-bootstrap

When the **actual executor/session inside the Antigravity IDE/2.0 surface** is asked to connect to, continue from, discover, or validate AgentOS ONE, it MUST read and follow:

`.agents/skills/agentos-one-onboarding/SKILL.md`

For Oracle-hosted Antigravity, fresh-session continuity is provided primarily by the global Antigravity `PreInvocation` hook installed in `~/.gemini/config/hooks.json`.

Fresh continuation selection is owned by ONE, not by the IDE workspace. `agent_core/active_continuation.py` maintains a Realm/runtime-level `agentos.active-continuation/v1` pointer containing only `project_id + index_id + ir_id`. That pointer is **not a second state store**: the authoritative working state remains the referenced Canonical IR generation.

Before the first model call, the hook reads that active selector, resolves the selected canonical project, verifies that the selector's `index_id`/`ir_id` still match the current `agentos.execution-head/v1` + `agentos.ir/v1` generation, then injects a bounded `source=ONE_PREINVOCATION_IR` envelope. If the selector is stale or invalid, the hook fails closed.

`workspacePaths` are environment metadata only. A fresh conversation opened in `/home/ubuntu/acas`, under `agentmanager/workspace/...`, or in another IDE workspace MUST NOT use that path to choose durable continuation. Workspace enumeration, Pulse/PM2 state, local memory, or vendor conversation history must never replace the ONE-selected Canonical IR.

The existing canonical publisher in `agent_core/project_continuation_index.py` is initially restricted to `agentos-core`; it atomically publishes `execution-head.json` and `continuity/latest.json` with one shared `index_id`. The selector may point only to an actually current canonical generation. Until project publishing is deliberately generalized, do not fabricate cross-project IR by scanning workspaces.

The `agentos-one` MCP server remains the explicit live-query surface (`one_status`, `one_bootstrap`, `one_capabilities`, `one_resolve`). The PreInvocation hook and MCP adapter both use the trusted Oracle-local read-only projection and expose no Realm/node credential to the model.

Executor identity and connectivity are separate claims. The PreInvocation hook may bind built-in Gemini/Codex identity only from its current `modelName`. The generic MCP process has no trustworthy caller-model context and therefore reports an unbound Antigravity executor identity rather than pretending the caller is Gemini or Codex.

If the active selector, Canonical IR head, or generation fence is unavailable/malformed/stale, fail closed with `ONE_IR_HEAD_UNRESOLVED`; do not reconstruct current state from local evidence.

If Oracle bootstrap is not installed, use the immutable bootstrap path documented by the onboarding skill. For enrolled external clients, use the client installer described there instead; do not make a desktop executor own Realm credentials.

Important identity fence: built-in Antigravity Gemini, built-in Antigravity Codex, `agy`, standalone `gemini`, Claude, and Codex CLI are distinct executor/provider identities. One is not acceptable evidence for another.

A fresh Antigravity executor must be able to recover the ONE-selected canonical IR/goal/authority state without copied vendor conversation history before cross-executor integration is considered complete.

## Current architectural role

AgentOS currently contains, among other components:

- continuation-state reconciliation;
- persistent control-plane coordination;
- session lifecycle / handoff persistence;
- governance and capability responsibility resolution;
- resource/world-state registry;
- Realm cross-node execution surfaces;
- platform runtime drivers;
- operational evidence and drift guards.

The model-independent **Cognitive IR / zero-cost arbitrary model switching** layer is still research unless and until a repeatable benchmark proves it. The existing `agentos.ir/v1` continuation contract is an implemented canonical continuation representation; that does not by itself prove the broader Cognitive IR research claim.

## Critical constraints

- Preserve Logic/Data separation: mutable user/project state must not be accidentally committed into the logic repository.
- Discover/resolve existing capability ownership before creating parallel infrastructure.
- Newer user intent must never be rolled back by stale snapshots, replay, or tool results.
- Evidence and tool results do not silently rewrite user intent.
- Claims in documentation must be backed by implementation paths; verified claims also need tests/evidence.
- **Capability does not imply authority.** A tool being available, a reachable transport/runner, or a PR being mergeable does not authorize another class of operation.

## Transport Routing Authority Rule

For AgentOS Realm/Node/control-plane work, transport selection is authority-driven rather than convenience-driven. Read `docs/CHATGPT_ONE_TRANSPORT.md` and `governance/transport-routing.json`.

Typed control-plane intents may use, in priority order when available:

1. native/direct ONE transport;
2. an AgentOS MCP/App bounded adapter;
3. the current ChatGPT Bootstrap Control Inbox (#50).

**GitHub Actions is not a generic fallback for control-plane work.** If all authorized ONE-side transports are unavailable or fail, surface that failure. Do not start or repurpose a workflow merely because a GitHub Actions runner can reach Oracle.

GitHub Actions is an allowed carrier only for an explicitly classified workflow intent such as CI/tests, build/package, explicit release/deployment, or a separately authorized evidence workflow.

Evaluate typed routing with `agent_core.transport_routing.resolve_transport`. Unknown intent classes and unauthorized requested transports fail closed.

## Protected Branch Authority Rule

For `main`, `master`, and `release/*`:

1. agents may create branches, commits, tests, reviews, and pull requests;
2. agents may report a PR as `READY_FOR_MERGE`;
3. agents MUST then stop at `AWAITING_HUMAN_APPROVAL`;
4. CI success, mergeability, positive review, or a generic `continue` instruction are not merge authorization;
5. do not merge or directly push to a protected branch without a separate explicit human authorization event.

Evaluate the executable policy with:

```bash
python3 scripts/protected_branch_authority.py \
  --branch main \
  --actor-kind agent \
  --via-pull-request
```

The expected result without explicit human approval is `AWAITING_HUMAN_APPROVAL` and a non-zero exit status.

## Documentation Reality Rule

Architecture-sensitive implementation changes MUST update at least one authoritative entry-point document in the same change set:

- `README.md`
- `docs/CURRENT_STATE.md`
- `ONBOARDING.md`
- `AGENTS.md`

Run:

```bash
python3 scripts/documentation_reality_guard.py
```

CI enforces the same rule. Treat a documentation-drift failure as an architecture regression, not optional cleanup.

## Useful verification

```bash
python3 scripts/continuation_state.py --self-test
python3 -m unittest tests.test_continuation_state tests.test_control_plane -v
python3 -m unittest tests.test_protected_branch_authority -v
python3 -m unittest tests.test_transport_routing -v
python3 scripts/documentation_reality_guard.py
```

## Git reporting

After pushing changes, report the remote/branch and latest commit hash.
