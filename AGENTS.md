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

## Critical Constraint
Never create real files named `STATUS.md` or `memory/` here.
They MUST be symlinks to `~/agent-data/projects/agentmanager/`.

## Git Push Reporting
After pushing changes, report the pushed remote/branch and the latest commit hash.
Example: `origin/main @ 4639f87`.
