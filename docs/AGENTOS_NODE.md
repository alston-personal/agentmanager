# AgentOS Node Contract v0.1

`agentos-node` is the node-local canonical discovery and responsibility-resolution surface. It is not a second manager, a second role registry, or an authority-granting shell bridge.

## Runtime entrypoint

On the Oracle self-hosted node identity:

```text
/home/agentos-node/.local/bin/agentos-node
```

The runtime bundle is derived from the AgentOS logic repository and reads mutable state from `/home/ubuntu/agent-data`.

## Harvest

```bash
agentos-node harvest
```

Harvest advertises what the node surface can route/query/observe. It may include governance, resource, resolve, runtime/surface, and other registered capabilities depending on the installed node version.

Examples from the original v0.1 surface include:

- `governance.resolve`
- `governance.get`
- `governance.list`
- `resource.query`
- `resource.register`
- `resource.verify.site`

The authoritative capability set is the node's live advertisement/NodeRegistry record, not this illustrative list.

## Capability semantics

Keep four states separate:

```text
advertised capability
    != routable transport
    != authorized effect
    != successful execution
```

Rules:

- Harvest/NodeRegistry capability advertisement is descriptive; it does not grant authority.
- ONE/ControllerService may be reachable even when the target node does not advertise the requested capability.
- A `NODE_CAPABILITY_NOT_ADVERTISED` result after ControllerService entry is a node-readiness/capability-convergence outcome, not evidence that the Core controller route is missing.
- A capability that is advertised still requires whatever governance/effect authorization applies before mutation.
- Architecture diagrams and expected capabilities are not substitutes for live capability advertisement.

## Responsibility resolution

Before implementing reusable or cross-project capability:

```bash
agentos-node governance resolve capability://network.port.allocate
```

Expected established ownership example:

```text
manager://port
```

An active exclusive owner means the caller must reuse/extend that owner instead of creating a competing implementation.

Examples:

```bash
agentos-node governance get role://governance.spec_steward
agentos-node governance list --kind manager
agentos-node governance list --kind role
```

## World-model query

```bash
agentos-node resource get site://studio.milkcat.org
agentos-node resource list --kind site
```

If a registered resource is fresh, use it. Only stale/unverified records should invoke targeted verification:

```bash
agentos-node resource verify-site site://studio.milkcat.org
```

## Project identity and source authority

Project identity is not the repository or checkout path.

Canonical Project Identity is owned by the AgentOS project store / resolver and projected into Governance Directory. A node may expose/query project information, but it must not infer canonical identity from its local filesystem.

A canonical project separates:

```text
project_id
aliases
source repo/branch
canonical source path
source node
state/data location
runtime/deployment location
```

For mutation, project/source integrity must be resolved before acting. A local checkout that merely looks like the right repository is not sufficient source authority.

## Canonical authority boundaries

The node surface is an index/router over existing authorities:

| Concern | Authority |
|---|---|
| Role semantics | `.agent/roles/registry.yaml` |
| Responsibility/provider resolution | Governance Directory |
| Canonical Project Identity / source locator | Project Store + canonical resolver, projected to Governance Directory |
| World/environment state | Resource Registry |
| Port allocation | `manager://port` / Port Manager |
| Node liveness/capability advertisement | NodeRegistry / live node heartbeat |
| Core deployed generation | Core deployment authority state |
| Execution authorization | Governance / effect-derived authority |
| Execution proof | receipts/evidence |

`agentos-node` must not silently take ownership from those components.

## Required executor startup protocol

For system/cross-project work:

```text
1. harvest / inspect live node capabilities
2. resolve canonical project identity when project-scoped
3. governance resolve(required capability/responsibility)
4. query relevant registered resources
5. targeted verify only if stale/missing
6. reuse/extend active owner
7. only if unresolved: discover -> register provider/resource
8. authorize effect
9. execute
10. persist receipt/evidence
```

This protocol operationalizes:

> Discover before invent. Resolve before implement. Verify before trust.

## Node Map / heartbeat rules

The Realm Node Map is ONE-side persistent state. A node should be treated as live only when runtime evidence supports enrollment/status/heartbeat freshness.

Do not:

- count a conceptual ChatGPT/PC surface as a live Realm node without enrollment evidence;
- infer freshness from a stale manifest alone;
- infer capability from intended role or source code presence;
- infer Node readiness from Core `/health` or ControllerService reachability.

For Golden Path work, preserve heartbeat provenance, advertised capability set, runtime/version provenance where relevant, and the final action receipt.

## Core / Node failure boundary established by Issue #64

On 2026-08-28 the real Control Inbox path was used to test `agent.surface.inspect` for `vopc5750`.

The request reached ControllerService, proving the Core route was alive, but the target node did not advertise the capability. The resulting node-level outcome was therefore the correct boundary.

This establishes the debugging order:

```text
transport
 -> ONE / controller route
 -> ControllerService
 -> node presence / heartbeat
 -> capability advertisement
 -> effect authority
 -> node execution
 -> receipt
```

Do not reopen or modify Core routing merely because a downstream node capability is missing unless fresh evidence shows the controller path itself has regressed.

## Historical verified evidence

The 2026-08-25 Oracle validation proved the original v0.1 discovery/governance/resource surface, including runtime entrypoint installation, governance/resource harvest, exclusive responsibility resolution, registered resource query, and Governance Directory audit.

That evidence remains valid for those behaviors, but its enumerated capability list is not a permanent complete Node contract. Newer node/runtime capabilities must be verified from live advertisement and receipts.
