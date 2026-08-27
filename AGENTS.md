# AgentOS — agentmanager Project Context

This repository is the **AgentOS logic/runtime root**. Mutable project state belongs in the configured data layer; runtime semantics, contracts, tests, governance, and automation live here.

## Required reading order

Before architecture or system-level changes:

1. `README.md` — current product goal and public architecture.
2. `docs/CURRENT_STATE.md` — canonical map of **Implemented / Verified / Research** capabilities.
3. `docs/AGENTOS_NODE.md` — responsibility/resource discovery contract for cross-project work.
4. `.agent/closure/ledger.yaml` — current Closure Reality for partially completed capabilities.
5. `.agent/CONSTITUTION.yaml` and relevant governance/role sources when authority or policy is involved.

Do not rely on older memory/pulse-era documents as current architecture if they disagree with `docs/CURRENT_STATE.md` and executable evidence.

## Current architectural role

AgentOS currently contains, among other components:

- continuation-state reconciliation;
- persistent control-plane coordination;
- session lifecycle / handoff persistence;
- governance and capability responsibility resolution;
- resource/world-state registry;
- Realm cross-node execution surfaces;
- platform runtime drivers;
- operational evidence and drift guards;
- a minimal employee-runtime slice for durable AgentInstance identity, employee-scoped memory namespace, assignment state, executor rebinding, and local durable agent messaging.

The employee-runtime slice is **not yet a closed multi-agent organization runtime**. Role inheritance/skill hydration, live Spec Steward operation, cross-node messaging, and Cognitive Thread integration still require evidence.

The model-independent **Cognitive IR / zero-cost arbitrary model switching** layer is still research unless and until a repeatable benchmark proves it.

## Critical constraints

- Preserve Logic/Data separation: mutable user/project state must not be accidentally committed into the logic repository.
- Discover/resolve existing capability ownership before creating parallel infrastructure.
- Newer user intent must never be rolled back by stale snapshots, replay, or tool results.
- Evidence and tool results do not silently rewrite user intent.
- Claims in documentation must be backed by implementation paths; verified claims also need tests/evidence.
- **Capability does not imply authority.** A tool being available or a PR being mergeable does not authorize a protected-branch mutation.
- **Implementation does not imply closure.** Use `.agent/closure/ledger.yaml`; do not describe a capability as operating/guarded/closed without the evidence required for that stage.
- **No silent park.** Important deferred work must retain owner, stage, gaps, and a return/validation condition in durable state.

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

## Closure Reality Rule

Run:

```bash
python3 scripts/closure_audit.py --summary
```

Lifecycle stages are:

`DISCOVERED -> SPECIFIED -> PROTOTYPED -> IMPLEMENTED -> INTEGRATED -> VERIFIED -> OPERATING -> GUARDED -> CLOSED`

Do not skip evidence gates. In particular, a unit test does not by itself prove `OPERATING`, and a successful live run does not by itself prove `GUARDED`.

## Useful verification

```bash
python3 scripts/continuation_state.py --self-test
python3 -m unittest tests.test_continuation_state tests.test_control_plane -v
python3 -m unittest tests.test_protected_branch_authority -v
python3 -m unittest tests.test_employee_runtime -v
python3 scripts/closure_audit.py --summary
python3 scripts/documentation_reality_guard.py
```

## Git reporting

After pushing changes, report the remote/branch and latest commit hash.
