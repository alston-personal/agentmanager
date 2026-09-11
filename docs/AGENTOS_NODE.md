# AgentOS Node / Realm Map Contract

**Status:** canonical Core Node documentation, 2026-09-11.

`agentos-node` and the ONE-side `NodeRegistry` are the canonical discovery/topology surfaces for AgentOS Nodes. They are not a second role registry, an executor registry by implication, or an authority-granting shell bridge.

## Identity model

Keep these identities separate:

- **Realm** — membership/control domain.
- **Node** — durable Realm participant with transport identity and heartbeat.
- **Surface / extension** — e.g. Antigravity Gemini, OpenAI Codex IDE, Anthropic Claude Code extension.
- **Executor adapter** — capability provider attached to a Node/surface.
- **Backend/model** — actual model/provider behind an executor; may be unknown or differ from extension brand.
- **Session/thread** — ephemeral execution instance.

Canonical invariants:

```text
Node online != executor available
advertised != routable != authorized != successful
surface identity != backend/model identity
```

## Node Registry / Node Map

`agent_core/node_registry.py` persists `agentos.node-registry/v0.1` and projects read-only `agentos.node-map/v0.1`.

A Node manifest includes Node identity/role, hostname/platform, capabilities, tool presence, surface inventory, runtime provenance, workspace-root policy, timestamps and bounded benchmark projection where present.

The map is generated from ONE-side state. It is not a hand-maintained inventory. Known deployed identities such as `oracle-core-node` and `vopc5750` are examples, not a complete hard-coded Realm.

Reported `online` becomes effectively `offline` when heartbeat freshness expires. Executor availability is a child layer and requires its own evidence.

## Capability / authority semantics

A capability is a declared/routable contract, not permission by itself. The controller must separately resolve authority.

Current bounded Oracle runtime convergence semantics:

- `node.runtime.converge` is typed, not a generic shell carrier;
- source repository/ref are allowlisted to AgentOS Core integration authority;
- caller supplies an exact accepted commit, not executable/module/argv/shell/service/path/environment authority;
- the governed ref is snapped for lane-membership proof;
- the requested exact commit is fetched independently and must be an ancestor of that snapped allowlisted ref;
- runtime bytes/installers are materialized only from the exact requested commit;
- a later concurrent merge advancing `core/integration` does not invalidate the already-authorized immutable rollout;
- health/profile/rollback remain part of acceptance.

This replaces the earlier moving-head equality assumption exposed by #117 live rollouts and fixed by #320/#322.

## Action Relay capability publication

Capability publication into the shared Action Relay boundary is itself governed runtime state, not a casual file copy.

Current accepted source rules include:

- publish through the fixed `agentos` group execution boundary;
- verify effective publisher GID and parent spool GID;
- create a unique same-directory temporary inode;
- write/fsync, atomic replace, and fsync the parent directory;
- do not seize ownership/delete historical foreign-owned temp evidence merely to make rollout pass;
- anchor Python imports to the immutable runtime root so `scripts/agentos_node.py` cannot shadow the real `agentos_node` package;
- capability marker presence proves publication/prerequisites only, not job authorization or terminal success.

The Worker Host uses the same principle: required group transition must occur before `no_new_privs` is locked, rather than assuming supplementary group state survives indefinitely in a long-lived service manager.

## Executor / surface visibility

`surface_inventory` describes topology only. Do not infer an executor is usable because an IDE extension is installed.

Where known, executor observability should expose:

- executor/surface identity;
- backend identity/provenance or `unknown`;
- availability/freshness;
- declared capabilities;
- routability and authorization separately;
- last sanitized terminal evidence;
- credential boundary.

The visual Realm map consumes this canonical topology instead of creating a second topology database. #152 continues first-class Node↔executor lifecycle extraction.

## Employee runtime relationship

Product/role Employees are not Nodes and are not equivalent to executors. Durable Employee identity/assignment/lease lives in ONE organizational state; Nodes/executors provide governed execution surfaces.

Recent #238 safety decisions:

- an Employee wake delivery may not remain `queued` forever when the Node receipt is absent; after the source-owned bounded wait it becomes `unknown` with `node_receipt_timeout`, without blind redispatch of the same presence;
- a product worker child is launch-eligible only after the exact Supervisor/S4 delivery satisfies the governed `awaiting_claim` contract;
- the child repeats that same check immediately before claim to preserve TOCTOU safety.

These are state-machine rules, not new execution authority.

## Runtime entrypoint / discovery

On the Oracle self-hosted Node identity the historical installed CLI entrypoint is:

```text
/home/agentos-node/.local/bin/agentos-node
```

Mutable Realm/Node/project state remains external under Agent Data. Exact live runtime generation/profile must come from runtime inspection and receipts, never inferred from an install path or repository head.

## Canonical authority boundaries

| Concern | Authority |
| --- | --- |
| Role semantics | `.agent/roles/registry.yaml` |
| Responsibility/provider resolution | Governance Directory |
| World/environment state | Resource Registry |
| Project identity/repo ownership | `docs/PROJECT_REPO_MAP.md` + project registry |
| Durable continuation | ONE Canonical IR + active continuation selector |
| Reusable learned experience | accepted ONE Experience artifacts |
| Employee identity/assignment/lease | ONE Employee Runtime state |
| Node membership/liveness/capabilities | ONE Node Registry / Node Map |
| Executor liveness | explicit executor/provider evidence, not Node status |
| Execution authorization | governance/effect-derived authority + controller routing |
| Runtime generation acceptance | exact source/runtime receipt + health/profile evidence |

## Evidence rule

Evidence must prove the exact layer claimed:

- heartbeat proves Node freshness, not executor success;
- capability advertisement proves declaration/prerequisites, not authority;
- ONE submission proves routing/acceptance, not workload success;
- executor terminal receipt proves that declared job result, not publication authority;
- exact source SHA proves source identity, not automatically service/profile convergence;
- an Employee wake receipt proves delivery/terminal state, not permission to retry an ambiguous external effect.

This layered rule prevents topology and capability growth from silently becoming privilege growth.
