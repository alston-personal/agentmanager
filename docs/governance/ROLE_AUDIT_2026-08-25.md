# AgentOS Role Audit — 2026-08-25

## Executive conclusion

The original LeopardCat role model remains conceptually useful, but it has accumulated a serious governance weakness: roles are mostly prose identities, while actual runtime behavior is not required to attest which role/policy version it loaded.

The system therefore risks **semantic drift** even when every individual change appears reasonable.

The corrective architecture is:

```text
AgentOS Constitution
        ↓
Versioned Role Registry
        ↓
Canonical IR / Capability Contracts
        ↓
Runtime Policy Attestation
        ↓
Receipts + Evidence
        ↓
Drift Guard / Spec Steward / periodic canaries
```

## Role-by-role audit

### `core.root` — LeopardCat Root

**Decision: KEEP, REWRITE REQUIRED**

Strengths:
- provides a shared identity/foundation concept;
- already distinguishes global law and local write scope.

Problems:
- the statement that physical disk state is the primary truth predates Canonical IR and Resource Registry;
- current AgentOS has multiple truth classes: durable logic, declared state, observed state, verified evidence, mutable memory;
- a foundation role must be executor/model independent.

Migration direction:
- replace “disk is truth” with provenance-aware truth;
- require VERIFIED / RECONSTRUCTED / UNKNOWN distinctions;
- load Constitution before sector personality.

### `sector.paw` — The Paw

**Decision: KEEP**

Purpose should narrow to deterministic implementation/execution after specification approval.

Keep:
- coding, tests, migration, implementation;
- concrete receipts and evidence.

Remove/avoid:
- architecture policy decisions that belong to Weaver;
- governance exceptions decided locally;
- arbitrary cross-project access.

### `sector.claw` — The Claw

**Decision: KEEP, NARROW TO ASSURANCE**

Current Claw mixes security audit, destructive QA, compliance and housekeeping authority.

New boundary:
- adversarial testing;
- security validation;
- failure-mode analysis;
- compliance evidence;
- may block, but does not silently redesign or implement the fix.

This preserves independent verification.

### `sector.weaver` — Weaver

**Decision: KEEP, PROMOTE**

This is one of the most strategically important roles.

It should own:
- Canonical IR;
- specifications;
- architecture decisions;
- acceptance criteria;
- capability boundary design;
- handoff contracts to Paw/Claw.

Its old requirement to compare against AICC should become a general historical/decision-record consultation requirement rather than a permanent dependency on one legacy repo.

### `sector.whisperer` — Whisperer

**Decision: KEEP, MAKE PHASE-SCOPED**

The creative/ideation role is valuable, but rules such as “禁止規格先行” must only apply during exploration.

Correct contract:
- may explore freely;
- may produce prototypes and concepts;
- must clearly label them non-authoritative;
- must hand off to Weaver before becoming formal architecture or production work.

### `governance.spec_steward` — Spec Steward

**Decision: KEEP, MOVE FROM PROJECT INSTANCE TO SYSTEM GOVERNANCE**

This role already addresses one form of drift: specifications that gradually stop matching implementation.

It should be continuously executable, not only descriptive.

Required checks:
- owner exists;
- target project exists;
- acceptance criteria exist;
- implementation evidence exists;
- required capability has a provider;
- stale/open specs are surfaced;
- closure or deprecation is explicit.

### `governance.keeper` — Constitution Keeper

**Decision: NEW, REQUIRED**

Purpose:
- protect immutable/core AgentOS invariants;
- validate role contracts;
- produce policy attestation;
- block silent constitutional drift;
- require migration records for intentional core changes.

It must not become an implementation executor.

### `system.cartographer` — Cartographer

**Decision: NEW, REQUIRED**

The Resource Registry work exposed a previously missing role: someone must own the world model.

Purpose:
- maintain declared / observed / verification state;
- query registry first;
- targeted verification only when stale/missing;
- prevent repeated rediscovery and hallucinated environment topology.

### `governance.arbiter` — Arbiter

**Decision: PROPOSED**

Needed because future AgentOS will increasingly face conflicts such as:
- UX speed vs safety;
- Paw implementation preference vs Claw risk finding;
- two capabilities claiming overlapping ownership;
- spec priority conflicts;
- user intent conflicting with old policy.

Arbiter resolves/escalates conflicts, but does not execute work.

### `knowledge.chronicler` — Chronicler

**Decision: PROPOSED**

Needed to prevent decisions from living only in chat history or stale Current Pulse sections.

Purpose:
- record architectural decisions;
- record constitutional migrations;
- record important capability births/deprecations;
- link evidence and receipts to the system Chronicle.

## Stale role instance finding

`instance.agentmanager_paw` is explicitly classified as **stale**.

It contains time-bound statements about LAMP, Cat-Ink/watchdog and a specific next Git push. These are historical state, not role identity. Runtime must never interpret this document as current system truth.

Future instance files must not contain unbounded “Current Pulse” sections. Mutable pulse belongs in Agent Data.

## Anti-drift model

AgentOS drift occurs in at least six forms:

1. **Policy drift** — principles gradually change meaning.
2. **Role drift** — role responsibilities overlap or silently expand.
3. **Spec drift** — implementation diverges from accepted design.
4. **Capability drift** — duplicated providers or hidden cross-project coupling appear.
5. **World-model drift** — environment facts become stale but remain trusted.
6. **Experience drift** — different executors/models produce materially different AgentOS behavior.

No single memory mechanism solves all six.

## Required controls

### 1. Constitution

Machine-readable invariants in `.agent/CONSTITUTION.yaml`.

Immutable principles are separately pinned in `.agent/governance/immutable_baseline.yaml`.

### 2. Role Registry

`.agent/roles/registry.yaml` defines:
- stable role IDs;
- status (`active`, `proposed`, `deprecated`, `stale`);
- purpose;
- required principles;
- authority boundaries;
- inputs/outputs/capabilities.

### 3. Policy attestation

Every important runtime/executor receipt should eventually carry:

```json
{
  "constitution_version": "2026.08.25.1",
  "role_set_version": "2026.08.25.1",
  "constitution_sha256": "...",
  "role_registry_sha256": "..."
}
```

This makes stale-policy execution detectable rather than invisible.

### 4. Drift Guard

`scripts/drift_guard.py` currently validates:
- immutable principles remain present and unchanged;
- immutable principles are not downgraded;
- roles reference real principles;
- active role sources exist;
- required governance roles exist;
- protected artifacts exist;
- stale legacy role instances are surfaced;
- a policy attestation can be emitted.

### 5. Spec Steward

Continue current spec drift scanning, then extend it to acceptance criteria and evidence linkage.

### 6. Golden governance canaries

Future work should add model-independent scenarios, for example:

- executor is asked to claim a deployment without a receipt → must refuse/mark unknown;
- executor is asked to bypass a project capability boundary → must route through registry;
- environment information is stale → must targeted-verify rather than blindly trust or full-scan;
- a weak executor receives Canonical IR → must preserve minimum Master Experience Floor behavior.

These canaries test **behavior**, not only files.

### 7. Evolution protocol

Core rules must never be treated as permanently frozen. The correct protection is controlled evolution:

```text
proposal
→ decision record
→ version bump
→ migration plan
→ drift/canary validation
→ activation
→ old version deprecated
```

This prevents both uncontrolled drift and governance fossilization.

## Immediate next actions

1. Rewrite `base_role.md` against Constitution v0.1.
2. Rewrite the four sector roles as contracts rather than personality-only prose.
3. Move `agentmanager_paw` Current Pulse to Agent Data and deprecate the role instance.
4. Promote Spec Steward into a runtime governance capability.
5. Add policy attestation to executor/action receipts and node harvest.
6. Add Arbiter only after conflict semantics are specified.
7. Add Chronicler together with formal decision-record schema.
8. Add behavioral governance canaries for Master Experience Floor and capability boundaries.

## Guiding principle

> AgentOS should not preserve old text unchanged forever. It should preserve **invariants, provenance, decisions, and migration paths**, while allowing implementations and roles to evolve deliberately.
