# Spec Steward O3 persistent Employee acceptance

Issue: #197

This slice source-controls the first durable `governance.spec_steward` Employee bootstrap and a read-only O3 evidence inspector.

## What bootstrap does

`ensure_spec_steward()` idempotently materializes:

- Employee `agentos-spec-steward`
- role `governance.spec_steward`
- skill `spec.audit`
- bounded WorkItem / assignment `spec-steward-o3-acceptance-v1`
- initial Cognitive Thread head

It does **not** bind an executor, create Employee presence, enable Supervisor delivery, dispatch through ONE, mutate Oracle service state, publish protected main, or emit the O3 VERIFIED marker.

## What the inspector proves

`inspect_spec_steward_acceptance()` is read-only. It cross-checks persisted evidence for:

- exact Employee / WorkItem / assignment contract
- active machine-hydrated role and skill
- governed `one_direct` wake delivery under `core-supervisor-employee-wake-v1`
- immutable Supervisor reconcile records covering initial lease generation and resumed lease generation
- resumed lifecycle lease with prior execution state `unknown`
- progressed thread head
- privacy-safe live executor/session transition witness
- role-authorized private `governance_evidence` continuity record
- completed sanitized Employee receipt
- carrier / authority evidence

The inspector may report `ready_for_live_marker=true` when persisted evidence is complete, but it always reports `verified_marker_emitted=false`.

## Live acceptance remains separate

`SPEC_STEWARD_PERSISTENT_EMPLOYEE=VERIFIED` requires a real fresh executor/session transition against a live governed ONE path. Static CI, synthetic fixtures, source-controlled role status, bootstrap success, or a merely reachable Node are not operating evidence.

The live witness must not contain raw session identity or credentials. Presence generation is Node-location evidence only and is not treated as executor/session identity proof.

## Governance invariants

- Employee identity != executor/model/session/Node identity.
- Active role declaration != operating Employee evidence.
- Skill != capability authority.
- Wake selection != execution authority.
- GitHub Actions is not a control-plane fallback.
- Verification must not mutate the state being verified.
- Static CI cannot emit the O3 VERIFIED marker.
