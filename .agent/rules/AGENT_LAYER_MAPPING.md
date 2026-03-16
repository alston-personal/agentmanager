# Agent Layer Mapping

## Purpose
Define which Antigravity files belong in the logic repo (`agentmanager`) and which belong in the data repo (`my-agent-data`).

## Logic Layer
These define behavior, rules, workflows, and reusable capabilities.

Keep in `/home/ubuntu/agentmanager`:

- `.agent/AGENT_RULES.md`
- `.agent/SYSTEM_IDENTITY.md`
- `.agent/SHELL_COMMAND_RULES.md`
- `.agent/CROSS_PLATFORM_GUIDE.md`
- `.agent/PUSH_TO_EXISTING_REPO.md`
- `.agent/PUSH_TO_GITHUB.md`
- `.agent/README.md`
- `.agent/rules/`
- `.agent/scripts/`
- `.agent/workflows/`
- `.agent/skills/`
- `scripts/`
- `tg_bridge.py`
- `dashboard/`

## Data Layer
These store changing state, memory, status, and operational history.

Keep in `/home/ubuntu/agent-data`:

- `memory/SHORT_TERM.md`
- `memory/LONG_TERM.md`
- `memory/session_sync.md`
- `projects/*/STATUS.md`
- `projects/*/memory/`
- future `logs/`
- future conversation summaries and run artifacts

## Symlink Layer
These paths may exist in the logic repo, but should only point to the data repo.

Allowed symlinks in `/home/ubuntu/agentmanager`:

- `memory -> /home/ubuntu/agent-data/memory`
- `STATUS.md -> /home/ubuntu/agent-data/projects/ai-command-center/STATUS.md`
- `.agent/memory/session_sync.md -> /home/ubuntu/agent-data/memory/session_sync.md`
- `projects/*/STATUS.md -> /home/ubuntu/agent-data/projects/*/STATUS.md`
- `projects/*/memory -> /home/ubuntu/agent-data/projects/*/memory`

## Current Exceptions
These are not active logic/data paths and should be treated as historical artifacts:

- `.agent/backups/`
- `memory.local-backup-*`

## Current Status
As of 2026-03-16:

- root `memory/` is correctly linked to the data repo
- root `STATUS.md` is correctly linked to the data repo
- `.agent/memory/session_sync.md` is correctly linked to the data repo
- project `STATUS.md` files are linked to the data repo
- project `memory/` links exist where project memory exists in the data repo

## Decision Rule
Use this test for any new file:

- If it answers "how should the agent behave?" -> logic layer
- If it answers "what happened, what changed, what is the current state?" -> data layer
