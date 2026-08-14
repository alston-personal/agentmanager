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
2. Classify the project repository before registration:
   - **GitHub-backed (default for code projects):** create or verify `alston-personal/<project-name>`, initialize the local code repo, set `origin`, and record the remote URL.
   - **Local-only (explicit exception):** do not create a GitHub repo; record `repo_url: null` and the reason in the project metadata.
3. For GitHub-backed projects, complete the repository provisioning gate before marking registration successful:
   - confirm the GitHub account/org and repository name;
   - create the remote with the intended visibility;
   - initialize and push the first commit containing only logic-layer files;
   - verify `git remote -v`, the default branch, and the remote commit;
   - never add `STATUS.md`, `memory/`, or secrets to the code repo.
4. Create `/home/ubuntu/agent-data/projects/<project-name>/STATUS.md` if missing.
5. Create `/home/ubuntu/agent-data/projects/<project-name>/memory/`.
6. Store repository metadata in `/home/ubuntu/agent-data/projects/<project-name>/project.yaml`, including `actual_code_path`, `repo_url`, `repo_visibility`, and `repository_state` (`provisioned`, `local-only`, or `blocked`).
7. Update `/home/ubuntu/agent-data/DASHBOARD.md`.
8. Create local metadata bridge in `agentmanager/projects/<project-name>/`:
   - `STATUS.md` symlink
   - `memory/` symlink

## Notes

- Logic stays in `agentmanager`.
- State stays in `agent-data`.
- Do not place real status content inside `agentmanager/projects/`.
- A project is not considered fully registered until its repository state is explicit.
- If GitHub credentials or remote creation is unavailable, register as `blocked` or `local-only`; never silently imply that a remote exists.
