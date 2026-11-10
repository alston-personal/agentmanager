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
| IP provenance / employment boundary | `governance/ip-ownership-policy.json` + `docs/IP_PROVENANCE.md` |
| Governance query index | `/home/ubuntu/agent-data/governance/directory.json` |

The Directory **indexes and resolves** these authorities; it must not silently redefine them.

## Project presence versus execution authorization (source-selection guard)

**PROJECT_PRESENCE_NOT_EXECUTION_ALLOWLIST**: Project existence, registration, execution permission, and live health are independent questions. Never infer "project not registered", "project deleted", or "data polluted" from absence in `governance/execution-authority.json`. That file is a *bounded governed execution capability allowlist*, **not** a complete Project Registry.

Use this read-only lookup sequence before any project registration, recreation, migration, or authorization edit:

1. **Existence / identity:** Check the canonical Oracle Project state at `/home/ubuntu/agent-data/projects/<project_id>/project.yaml` (or configured `AGENT_DATA_ROOT`), and Project/Governance Directory `project://<project_id>` as a secondary index. Resolve aliases and canonical repository. Do not silently create an absent record.
2. **Resource / service identity:** Resolve `repo://`, `service://`, `path://` from the Resource Registry and Port Manager; report timestamps and evidence freshness. Repository source code and workflow references are historical/provenance evidence, not live Oracle verification.
3. **Execution authorization:** Only *after identity resolution*, check `governance/execution-authority.json` or the appropriate ONE capability policy for the **specific operation**. Missing capability means "not authorized in this checked surface/ref", *not* "project missing". Name the exact branch, registry version, scope and checked capability.
4. **Actual runtime:** Require a current authenticated ONE/Runtime receipt for online/deployed/executed claims. State "unverified" if runtime is unreachable; do not promote stale prior receipts to current health.
5. **Conflict handling:** If canonical Project data and indexes disagree, classify `registry_projection_drift` or `unverified_source_conflict`, capture evidence and reconcile through the existing owner. Never overwrite or duplicate-register based solely on a missing secondary projection.

Regression example: `if-tv-station` was incorrectly called "not registered" because it was missing from the `core/integration` execution-authority allowlist. That finding only supports "not present in that branch's *specific execution allowlist*". GitHub repo `alston-personal/if-tv-station` and historical Oracle service/paths are positive provenance, while live canonical registration must be checked independently. For the leopard-cat outro work, reuse product Issue `alston-personal/if-tv-station#3`; do not re-register the project or invent a dispatch receipt.

**Answer provenance rule:** For negative existence claims, record `lookup_target`, `source_kind`, `branch_or_version`, `observed_at`, `freshness`, `result` and whether canonical authority was actually queried. If canonical source was not accessible, the only supported conclusion is `canonical_state_unverified`.


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

Persistent runtime rule:

- A service MUST obtain or verify its port through `manager://port` before binding.
- `ensure <port> <service>` registers an unclaimed port or verifies the existing owner.
- `require <port> <service>` fails closed when the port is missing or owned by another service.
- Directly hard-coding and binding an unmanaged persistent service port is a governance violation.

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
