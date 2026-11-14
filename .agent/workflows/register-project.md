---
description: Register a project in the local agent-data layer and create the status bridge
---

# /register-project - Register Project

This workflow creates a project entry in the data layer and wires the local metadata bridge. **A local STATUS or Dashboard entry is not by itself a completed project registration.** Repository verification is a distinct fail-closed gate.

## Usage

```bash
python3 scripts/register_project.py <project-name> --display-name "Project Name" --repo-url https://github.com/alston-personal/<project-name>
```

## Steps

1. Validate the target project name and normalize it to `kebab-case`.
2. Classify the project repository before registration:
   - **GitHub-backed (default for code projects):** create or verify `alston-personal/<project-name>`, initialize the local code repo, set `origin`, and record the remote URL.
   - **Local-only (explicit exception):** do not create a GitHub repo; record `repo_url: null` and the reason in the project metadata.
3. For GitHub-backed projects, complete the repository provisioning gate before marking registration successful. The current `register_project.py` only **verifies** an already-provisioned repository; it does **not** create GitHub repositories or push commits. The existing authorized provisioning lane must do that first:
   - confirm the GitHub account/org and repository name;
   - create the remote with the intended visibility;
   - initialize and push the first commit containing only logic-layer files;
   - verify `git remote -v`, the default branch, and the remote commit. Pass `--repo-url` with the canonical HTTPS URL; the local HEAD on `main` must match `git ls-remote origin main`; otherwise `repository_state: blocked` and the CLI exits nonzero;
   - never add `STATUS.md`, `memory/`, or secrets to the code repo.
4. Create `/home/ubuntu/agent-data/projects/<project-name>/STATUS.md` if missing.
5. Create `/home/ubuntu/agent-data/projects/<project-name>/memory/`.
6. Store repository metadata in `/home/ubuntu/agent-data/projects/<project-name>/project.yaml`, including `actual_code_path`, `repo_url`, and `repository_state` (`provisioned` or `blocked` in the currently implemented CLI). Reconcile existing metadata rather than wiping it. `repo_visibility` and an explicit supported `local-only` CLI mode remain **follow-up gaps**, not completed functionality.
7. Update `/home/ubuntu/agent-data/DASHBOARD.md`.
8. Create local metadata bridge in `agentmanager/projects/<project-name>/`:
   - `STATUS.md` symlink
   - `memory/` symlink

## Notes

- Logic stays in `agentmanager`.
- State stays in `agent-data`.
- Do not place real status content inside `agentmanager/projects/`.
- A project is not considered fully registered until its repository state is explicit.
- If GitHub credentials or remote creation is unavailable, record `blocked`; never silently imply that a remote exists. An explicit local-only exception is described as a desired policy but is not yet supported by this CLI revision.
- **This repository verification gate does not write ONE canonical Project Registry or obtain a Runtime Receipt.** Those remain separate acceptance requirements.
