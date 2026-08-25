# AgentOS Governance Directory

## Purpose

The Governance Directory is AgentOS's **responsibility resolver and operational yellow pages**. It answers:

- Who owns this class of work?
- Does a reusable capability already exist?
- Which manager/service/provider should be used?
- Is that provider exclusive?
- Is the runtime evidence still fresh?

It exists to prevent organizational amnesia and duplicate capability growth.

> **Discover before invent. Resolve before implement. Verify before trust.**

## It is not a second constitution or role authority

Canonical sources remain separated by concern:

| Concern | Canonical source |
|---|---|
| AgentOS invariant principles | `.agent/CONSTITUTION.yaml` + immutable baseline |
| Role semantics/version | `.agent/roles/registry.yaml` |
| Resource/world model | `/home/ubuntu/agent-data/resources/registry.json` |
| Port allocation | `/home/ubuntu/agent-data/config/port_registry.json` via `manager://port` |
| Project state | `/home/ubuntu/agent-data/projects/*/project.yaml` |
| Governance query index | `/home/ubuntu/agent-data/governance/directory.json` |

The Directory **indexes and resolves** these authorities; it must not silently redefine them.

## Entity namespaces

- `role://` — versioned organizational roles mirrored from the canonical role registry.
- `manager://` — deterministic manager with an explicit authority boundary.
- `service://` — running/monitorable system service.
- `capability://` — a reusable ability that can be resolved to provider(s).
- `resource://` — world/environment resource.
- `policy://` — operational routing/coordination policy.
- `spec://`, `project://`, `node://` — references when needed by governance resolution.

## Runtime state

Directory entities use lifecycle states such as:

`declared → implemented → deployed → observed → verified`

and exceptional lifecycle states:

`stale`, `drifted`, `superseded`, `retired`.

A declaration does not prove runtime existence. A verified entity requires evidence and a verification timestamp.

## Resolve-first protocol

Before implementing any reusable cross-project/system capability:

1. Resolve the requested capability in the Governance Directory.
2. If an active exclusive owner exists, route to it. Do not implement a parallel owner.
3. If providers exist but none is exclusive, reuse or extend unless the specification explicitly justifies a new provider.
4. If resolution returns nothing, perform targeted discovery.
5. Register newly discovered reusable capability/manager/resource.
6. Verify observed runtime state before relying on stale facts.
7. Authorization remains governed by the Governance Registry/effect-derived authority; Directory resolution never grants permission by itself.

## Example: network port allocation

```bash
python3 scripts/governance_directory.py resolve capability://network.port.allocate
```

Expected owner:

`manager://port`

Only after resolution should an Agent request allocation:

```bash
python3 scripts/core_services/port_manager.py allocate layoutlab-api --desc 'Layout Lab API'
```

A conflicting explicit registration now fails rather than merely warning. Override requires an explicit `--force`, which is intended only after governance approval.

## Role model

`.agent/roles/registry.yaml` is canonical. The Directory mirrors it as `role://<stable-role-id>` so runtime agents can query it without duplicating role prose.

Examples:

- `role://core.root`
- `role://sector.weaver`
- `role://sector.paw`
- `role://sector.claw`
- `role://sector.whisperer`
- `role://governance.spec_steward`
- `role://governance.keeper`
- `role://system.cartographer`

Stale historical instances such as `role://instance.agentmanager_paw` remain queryable but are excluded from active resolution.

## Drift layers

Different controls cover different kinds of drift:

- `scripts/drift_guard.py`: Constitution + role contract drift and policy attestation.
- `scripts/spec_steward.py`: specification-to-project/capability drift.
- `scripts/governance_directory.py audit`: responsibility/provider/service/runtime freshness drift.
- Resource Registry verification: world-model drift.
- Behavioral canaries: executor/experience drift.

These controls are complementary; none should be rewritten as a competing all-purpose guardian.

## Governance invariant

The Directory may tell an Agent **where responsibility lives**, but it cannot create authority.

Resolution:

`Capability → Owner/Provider`

Execution still follows governance:

`Capability → Intent → Authorization → Ledger → Effect → Receipt`.
