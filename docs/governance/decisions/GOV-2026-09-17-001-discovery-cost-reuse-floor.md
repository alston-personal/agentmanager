# GOV-2026-09-17-001 — Discovery Cost Reuse Floor

Status: Proposed
Date: 2026-09-17
Scope: AgentOS Core / all project continuations

## Decision

AgentOS MUST treat sufficiently expensive discovery as reusable project knowledge instead of disposable session context.

If an agent spends meaningful effort locating, verifying, reconciling, or proving a stable fact, that fact SHOULD be promoted into the appropriate canonical project/data-layer representation before the task is considered fully closed.

A later agent MUST hydrate and reuse that canonical knowledge before performing equivalent discovery again.

The system MAY repeat discovery only when at least one material dimension differs:

1. **Scope** — the new task covers a different subsystem, repository, environment, actor, or boundary.
2. **Depth** — the new task requires stronger detail, implementation-level evidence, or a deeper causal explanation than the stored fact provides.
3. **Freshness** — the stored fact has an explicit TTL, known drift risk, or is old enough that revalidation is justified.
4. **Evidence strength** — the new task requires a stronger source class, runtime proof, test, receipt, or live verification than the stored evidence.
5. **Conflict** — current evidence disagrees with the canonical fact, requiring reconciliation rather than blind reuse.
6. **User intent change** — newer user intent changes the target or invalidates an earlier assumption.

Absent one of these conditions, repeating equivalent discovery is a regression in continuity quality.

## Why

Repeated rediscovery wastes model/tool budget, user time, and execution latency. It also increases the risk that different agents reach inconsistent answers about facts already established once.

Examples of promotable knowledge include:

- repository owner/name and canonical branch;
- production/runtime paths;
- service names and ports;
- deployment/build commands;
- source-tree anchors;
- capability ownership and responsibility maps;
- stable API endpoints;
- verified environment constraints;
- known privacy/security invariants;
- recurring operational caveats.

The goal is not to prevent verification. The goal is to prevent paying the same discovery cost twice without a reason.

## Promotion rule

Discovery should be promoted when all are true:

- the fact is likely to be reused;
- verification cost was non-trivial;
- the fact is stable enough to outlive the current turn/session;
- storing it does not violate privacy/security rules;
- there is an authoritative destination in the data layer or canonical IR path.

Promotion destinations follow Logic/Data separation:

- mutable project/runtime facts -> project data layer / project registry / canonical project state;
- reusable cross-project runtime semantics -> AgentOS logic/governance docs or executable policy;
- task-local ephemeral observations -> current continuation IR only;
- secrets/credentials -> never canonicalize as plaintext project knowledge.

## Required metadata

Promoted facts SHOULD carry enough metadata to determine whether reuse is still valid:

- `fact_key`
- `value`
- `scope`
- `depth`
- `source`
- `verified_at`
- `freshness_policy` or TTL when relevant
- `evidence_strength`
- `sensitivity`
- optional `supersedes`

The representation may differ by project/schema; semantic equivalence is sufficient.

## Hydration-before-discovery rule

Before starting repository/environment discovery, an agent SHOULD resolve in this order:

1. current continuation IR;
2. canonical project state / project registry;
3. authoritative runtime/resource registry;
4. only then perform new discovery for missing, stale, conflicting, deeper, or differently scoped facts.

The agent should explicitly distinguish:

- **reuse** — existing fact is sufficient;
- **revalidate** — same fact, freshness/evidence needs renewal;
- **deepen** — same topic, greater detail required;
- **expand** — new scope;
- **reconcile** — sources conflict.

## Discovery receipt

When meaningful discovery occurs, the continuation/result SHOULD record whether knowledge promotion happened:

```yaml
discovery:
  performed: true
  reason: missing | stale | deeper | expanded_scope | conflict | stronger_evidence
  reusable_facts:
    - fact_key: project.repo
      promoted: true
      destination: project_registry
```

This provides a machine-auditable signal that expensive exploration was not discarded.

## Security constraint

Canonical IR, project state, logs, and discovery receipts MUST sanitize credentials and bearer material before persistence. Repository remotes must be stored in credential-free form.

## Acceptance criteria

This decision is considered fully implemented only when executable behavior proves that:

1. project continuation hydrates existing project/runtime facts before broad discovery;
2. equivalent rediscovery can be skipped when scope/depth/freshness/evidence are already sufficient;
3. rediscovery has a machine-readable reason when it occurs;
4. newly verified reusable facts can be promoted into canonical project state;
5. credential-bearing values are sanitized before IR/state persistence;
6. regression tests cover reuse, stale revalidation, deeper exploration, scope expansion, conflict reconciliation, and credential sanitization.

## Non-goal

This decision does not require agents to trust stale or low-confidence data blindly. Revalidation remains correct when freshness, evidence level, conflict, or changed scope/depth justifies it.
