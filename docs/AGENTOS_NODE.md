# AgentOS Node / Realm Map Contract

**Status:** canonical Core Node documentation, 2026-09-04.

`agentos-node` and the ONE-side `NodeRegistry` are the canonical discovery/topology surfaces for AgentOS Nodes. They are not a second manager, a second role registry, an executor registry by implication, or an authority-granting shell bridge.

## Identity model

Keep these identities separate:

- **Realm** — membership/control domain.
- **Node** — durable Realm participant with transport identity and heartbeat.
- **Surface / extension** — e.g. Antigravity Gemini, OpenAI Codex IDE, Anthropic Claude Code extension.
- **Executor adapter** — capability provider attached to a Node/surface.
- **Backend/model** — actual model/provider behind an executor; may be unknown or different from the extension brand.
- **Session/thread** — ephemeral execution instance.

Canonical invariants:

```text
Node online != executor available
advertised != routable != authorized != successful
surface identity != backend/model identity
```

## ONE-side Node Registry

`agent_core/node_registry.py` persists `agentos.node-registry/v0.1` and projects the read-only `agentos.node-map/v0.1`.

A Node manifest records at least:

- `node_id` and role (`core` / `client`);
- hostname/platform metadata;
- declared capabilities;
- tool presence;
- `surface_inventory`;
- runtime provenance/state;
- safe workspace-root policy projection;
- manifest/heartbeat timestamps;
- bounded benchmark projection where present.

Registry writes are atomic and locked. Readers consume fully published files; a heartbeat may carry a fresh manifest so capability/runtime state and liveness advance together.

## Liveness semantics

The map distinguishes reported status from effective status. A Node reporting `online` is projected `offline` when its heartbeat becomes stale.

The stale threshold is configurable through `AGENTOS_NODE_STALE_SECONDS`, with a minimum of 15 seconds and a current default of 30 seconds.

Therefore old screenshots, manifests or source code cannot establish current Node liveness. Use the current Node Map / heartbeat evidence.

## Node Map projection

`agentos.node-map/v0.1` provides:

- Realm id;
- Node count and effective online count;
- sorted Node projections (Core first, then clients);
- Realm-level aggregate capabilities and tool presence from non-offline Nodes;
- aggregate surface providers from non-offline Nodes;
- runtime convergence policy plus counts for `converged`, `drifted`, and `unknown` Nodes.

Known real Node identities include `oracle-core-node` and the Windows client `vopc5750`. These are examples of accepted deployments, not a hard-coded complete Realm inventory.

## Capability semantics

A capability is a declared/routable contract, not permission by itself. The controller must separately resolve authority.

Recent canonical changes include the bounded Oracle runtime convergence path:

- `node.runtime.converge` is a typed semantic action;
- canonical source is restricted to `alston-personal/agentmanager` / `core/integration` / exact SHA;
- callers cannot supply executable, module, argv, shell, command, arbitrary path, service or environment;
- required installers/services are fixed in source;
- same-source convergence still reconciles the fixed operating profile;
- health and rollback are part of acceptance;
- sanitized terminal receipts preserve exact requested/previous/resulting source identity;
- GitHub Actions remains bootstrap/CI/deployment authority only and is not the steady-state control-plane fallback.

Capability markers must represent installed/usable prerequisites, not mere source-code presence. #242 closed the earlier gap where `oracle-core-node` could be online yet not advertise the accepted runtime convergence capability.

## Executor / surface visibility

`surface_inventory` is descriptive topology. It must not be used to claim an executor is live solely because a surface is installed.

Executor observability should expose, where actually known:

- executor/surface identity;
- backend identity and provenance or `unknown`;
- availability/freshness;
- declared capabilities;
- routability and authorization as separate fields;
- last sanitized successful/terminal evidence;
- credential boundary.

The visual Realm map tracked by #184 consumes this canonical topology rather than creating a second topology database. #152 owns remaining first-class Node↔executor inventory/liveness extraction.

## Runtime entrypoint / local discovery

On the Oracle self-hosted Node identity, the historical installed CLI entrypoint is:

```text
/home/agentos-node/.local/bin/agentos-node
```

The runtime logic is sourced from AgentOS Core while mutable Realm/Node/project state is external under Agent Data. Exact live runtime worktree/generation must be obtained from runtime inspection/receipts rather than inferred from this path.

## Harvest and responsibility resolution

`agentos-node harvest` advertises node-supported query/observation surfaces such as governance/resource discovery. Harvest describes what can be discovered or routed; it does not authorize execution.

Before implementing reusable or cross-project capability:

```text
1. harvest / inspect canonical capabilities
2. resolve responsibility/provider
3. query registered resources/world state
4. targeted verification only when stale/missing
5. reuse/extend the active owner
6. if unresolved, register through governed discovery
7. resolve effect authority
8. execute through the authorized transport/capability
9. persist a sanitized receipt/evidence
```

This is the operational meaning of:

> Discover before invent. Resolve before implement. Verify before trust.

## Canonical authority boundaries

| Concern | Authority |
| --- | --- |
| Role semantics | `.agent/roles/registry.yaml` |
| Responsibility/provider resolution | Governance Directory |
| World/environment state | Resource Registry |
| Project identity / repo ownership | `docs/PROJECT_REPO_MAP.md` + project registry |
| Durable continuation | ONE Canonical IR + active continuation selector |
| Reusable learned experience | accepted ONE Experience artifacts |
| Node membership/liveness/capabilities | ONE Node Registry / Node Map |
| Executor liveness | explicit executor/provider evidence, not Node status |
| Execution authorization | governance/effect-derived authority + controller routing |
| Runtime generation acceptance | exact source/runtime receipt + health/profile evidence |

`agentos-node` must not silently take ownership from these authorities.

## Evidence rule

A Node or executor claim should be considered live/verified only when the evidence proves the exact layer claimed. Examples:

- heartbeat proves Node freshness, not executor success;
- capability advertisement proves declaration/prerequisites, not authority;
- ONE submission proves routing/acceptance, not workload success;
- executor terminal receipt proves the declared job result, not protected publication authority;
- runtime source SHA proves source identity, not automatically service/profile convergence.

This layered evidence rule prevents topology and capability growth from becoming implicit privilege growth.
