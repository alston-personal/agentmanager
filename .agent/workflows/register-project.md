---
description: Register a project in the local agent-data layer and create the status bridge
---

# /register-project - Register Project

This workflow creates a formal project entry in the data layer and wires the local metadata bridge.

## Usage

```bash
python3 scripts/register_project.py <project-name> --display-name "Project Name"
```

## Steps

1. Validate the target project name and normalize it to `kebab-case`.
2. Create `/home/ubuntu/agent-data/projects/<project-name>/STATUS.md` if missing.
3. Create `/home/ubuntu/agent-data/projects/<project-name>/memory/`.
4. Update `/home/ubuntu/agent-data/DASHBOARD.md`.
5. Create local metadata bridge in `agentmanager/projects/<project-name>/`:
   - `STATUS.md` symlink
   - `memory/` symlink

## Notes

- Logic stays in `agentmanager`.
- State stays in `agent-data`.
- Do not place real status content inside `agentmanager/projects/`.
