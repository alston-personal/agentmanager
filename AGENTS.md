# AgentOS — agentmanager Project Context

> Global rules inherited from `~/.codex/AGENTS.md`. This file adds project-specific context only.

## Project Role
This is the **Logic Layer Root** of the AgentOS ecosystem.
- Manages all agent workflows, scripts, and capabilities.
- Project data lives at: `~/agent-data/projects/agentmanager/`

## Key Entry Points
- `ONBOARDING.md` — system state overview (read this first)
- `.agentos/development-context.json` — canonical development branch, write policy, branch registry, active work, and next actions (**read before any repository write**)
- `docs/CANONICAL_DEVELOPMENT_CONTEXT.md` — human-readable development continuity / branch consolidation record
- `DASHBOARD.md` — all registered projects
- `scripts/bootstrap.py` — repair symlinks
- `.agent/workflows/` — slash command definitions
- `docs/IDE_ADAPTER.md` — cross-IDE Distributed AgentOS continuity
- `docs/CONTINUITY_MIRROR.md` — private connector fallback for agents that cannot reach the Control Plane
- `contracts/execution-disposition-v1.json` — portable final/continue semantics
- `contracts/master-trace-exemplars-v1.json` — task-neutral long-horizon execution demonstrations
- `docs/MASTER_EXPERIENCE_REPRODUCTION_PROTOCOL.md` — blind reproduction/measurement protocol
- `docs/MASTER_EXPERIENCE_FLOOR.md` — normative cross-executor capability-normalization requirement

## Development Branch Continuity
For current AgentOS vNext work, `feature/distributed-agentos-runtime` is the canonical integration/continuation branch unless `.agentos/development-context.json` explicitly says otherwise.

Before **every repository write**:
1. Read/refresh `.agentos/development-context.json`.
2. Confirm repository, active branch, merge target, and write policy.
3. Pass the branch explicitly to the Git/GitHub write operation. Never rely on default-branch fallback.
4. Treat experimental writes to `main` as denied unless production promotion is explicitly intended and authorized.

Do not create a new branch merely because the task sounds like a new feature. Short-lived child branches are exceptional and must declare parent branch, merge target, purpose, and completion condition; merge/salvage them back promptly and retire them.

This rule is evidence-backed: on 2026-08-24 an Oracle probe write omitted the branch argument and landed on `main` despite the higher-level intent being experimental. AgentOS therefore treats branch/repo/write-policy/merge-target as execution constraints that must propagate to the final tool boundary, not as facts an executor is expected to remember informally.

## Distributed Continuity
Treat shared Canonical IR as the cross-agent continuity authority rather than the current IDE/chat session alone.

Preferred read order:
1. If the `agentos` CLI is configured and the Control Plane is reachable, run `agentos status` and use the returned project state.
2. If direct Control Plane access is unavailable but an authorized GitHub connector can read the private Data Layer, read `alston-personal/my-agent-data:projects/agentmanager/continuity/latest.json` and verify its Canonical IR digest.
3. For repository-development continuity, read `.agentos/development-context.json` and `docs/CANONICAL_DEVELOPMENT_CONTEXT.md` before falling back to ordinary repository/session reconstruction.
4. Fall back to ordinary repository/session context only when shared-state paths are unavailable; report that distributed continuity could not be consulted.

Operational rules:
- If the user says `continue`, prefer `agentos continue` when the Control Plane is available.
- Do not fork a new task when project state reports an existing `submitted`, `leased`, or `running` task.
- Use `agentos ask` only for a genuinely new goal and `agentos delegate <provider>` for explicit cross-provider delegation.
- `.agentos/project.json` is the stable, non-secret project identity marker and may be committed.
- `projects/<project-id>/handoff_capsule.md` is legacy human handoff text; do not treat it as newer than `continuity/latest.json`.

## Goal-level Execution Regime
For an active goal, **answerability is not completion**. A successful commit, test, tool call, receipt, completed subproblem, or useful progress report is not a terminal condition by itself.

Before yielding/finalizing, evaluate the parent goal using `agentos.execution-disposition/v1` semantics. If a material closure gap remains and the next action is derivable, authorized, and safe, continue the inspect -> act -> receipt -> reassess loop without requiring a human continuation pulse.

On a recoverable bounded failure: localize it, inspect authoritative state/implementation, apply the smallest repair, and revalidate. On mutable-state drift: refresh authoritative state before acting. On protected effects or new authority: stop before the effect and request authority; capability never grants permission.

When bootstrapping a fresh executor for long-horizon work, load the task-neutral exemplars from `contracts/master-trace-exemplars-v1.json`. These exemplars define execution behavior, not task answers. Preserve VERIFIED / RECONSTRUCTED / UNKNOWN distinctions.

## Master Experience Floor
Executor quality may raise the ceiling; AgentOS must defend the floor. Do not assume that a replacement model, provider, IDE, chat session, or reasoning-effort regime has the same native planning horizon or premature-finalization resistance.

For ordinary authorized work, a weaker executor must not force the human to become the scheduler. If the executor yields while the parent goal still has an authorized, safe, derivable material closure gap, treat that yield/final as a receipt and keep the Goal ACTIVE through external supervision/redispatch. Adapt slice size, scaffolding, verification density, and continuation policy to the observed executor rather than requiring the user to type `continue` or `?`.

Cross-model continuity is incomplete if only semantic state transfers while user-visible execution continuity collapses. Follow `docs/MASTER_EXPERIENCE_FLOOR.md` for the normative capability-normalization requirement.

## Critical Constraint
Never create real files named `STATUS.md` or `memory/` here.
They MUST be symlinks to `~/agent-data/projects/agentmanager/`.

## Git Push Reporting
After pushing changes, report the pushed remote/branch and the latest commit hash.
Example: `origin/feature/distributed-agentos-runtime @ <sha>`.
