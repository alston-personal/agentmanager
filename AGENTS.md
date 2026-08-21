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

## Distributed Continuity
When the `agentos` CLI is configured for the current environment, treat Control Plane Canonical IR as the cross-agent continuity authority rather than the current IDE/chat session alone.

- Run `agentos status` before resuming distributed work.
- If the user says `continue`, prefer `agentos continue` so the latest project Canonical IR is used.
- Do not fork a new task when project state reports an existing `submitted`, `leased`, or `running` task.
- Use `agentos ask` only for a genuinely new goal and `agentos delegate <provider>` for explicit cross-provider delegation.
- `.agentos/project.json` is the stable, non-secret project identity marker and may be committed.

If the Control Plane URL/token is not configured or reachable, continue with normal repository context and report that Distributed AgentOS continuity could not be consulted.

## Critical Constraint
Never create real files named `STATUS.md` or `memory/` here.
They MUST be symlinks to `~/agent-data/projects/agentmanager/`.

## Git Push Reporting
After pushing changes, report the pushed remote/branch and the latest commit hash.
Example: `origin/main @ 4639f87`.
