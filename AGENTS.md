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

## Token Efficiency
Default to compact execution and compact replies.
- Search narrowly before widening scope.
- Read files in small slices instead of dumping full contents.
- Summarize logs, diffs, and findings unless the user explicitly asks for raw output.
- For broad requests, work in phases and report only the highest-signal findings first.

## Search & Command Constraints
- **Search Narrowly**: Never run wide searches (e.g., `rg`, `grep`, `find`) on broad directories like `/home/dqa03` or `/`.
- **Exclude Large Folders**: Always filter/exclude directory paths containing database data (`*db_data*`), attachments (`*files*`, `*attachments*`), backups, and logs.
- **Use Timeouts**: Always attach a `timeout` limit (e.g., `timeout 10s`) when invoking external search tools in bash.

## Execution Discipline
When the user asks to implement or modify something, default to doing the work instead of restating intent.
- Do not enter an apology/promise/explanation loop.
- Do not claim a change was made unless the file was actually edited.
- Prefer reporting concrete artifacts: changed files, diff summary, and verification status.
- If the repo path or target file is unclear, verify location first instead of pretending progress.
- If a task is multi-step, finish at least one concrete step before giving a status update.
- If interrupted or a tool fails, resume from the last confirmed state and state the exact blocker in one sentence.

## Git Push Reporting
After pushing changes, report the pushed remote/branch and the latest commit hash.
Example: `origin/main @ 4639f87`.
