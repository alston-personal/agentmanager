# AgentOS — agentmanager Project Context

> Global rules inherited from `~/.codex/AGENTS.md`. This file adds project-specific context only.

## Project Role
This is the **Logic Layer Root** of the AgentOS ecosystem.
- Manages all agent workflows, scripts, and capabilities.
- Project data lives at: `~/agent-data/projects/agentmanager/`

## Key Entry Points
- `ONBOARDING.md` — system state overview (read this first)
- `DASHBOARD.md` — all registered projects
- `scripts/bootstrap.py` — repair symlinks
- `.agent/workflows/` — slash command definitions
- `docs/IDE_ADAPTER.md` — cross-IDE Distributed AgentOS continuity
- `docs/CONTINUITY_MIRROR.md` — private connector fallback for agents that cannot reach the Control Plane
- `contracts/execution-disposition-v1.json` — portable final/continue semantics
- `contracts/master-trace-exemplars-v1.json` — task-neutral long-horizon execution demonstrations
- `docs/MASTER_EXPERIENCE_REPRODUCTION_PROTOCOL.md` — blind reproduction/measurement protocol

## Distributed Continuity
Treat shared Canonical IR as the cross-agent continuity authority rather than the current IDE/chat session alone.

Preferred read order:
1. If the `agentos` CLI is configured and the Control Plane is reachable, run `agentos status` and use the returned project state.
2. If direct Control Plane access is unavailable but an authorized GitHub connector can read the private Data Layer, read `alston-personal/my-agent-data:projects/agentmanager/continuity/latest.json` and verify its Canonical IR digest.
3. Fall back to ordinary repository/session context only when neither shared-state path is available; report that distributed continuity could not be consulted.

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

## Critical Constraint
Never create real files named `STATUS.md` or `memory/` here.
They MUST be symlinks to `~/agent-data/projects/agentmanager/`.

## Git Push Reporting
After pushing changes, report the pushed remote/branch and the latest commit hash.
Example: `origin/main @ 4639f87`.
