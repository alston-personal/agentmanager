---
description: Initialize or update the Agent OS environment configuration (.env).
---
# ⚙️ /setup - Environment Initialization

Use this workflow to generate or update your `.env` file. This is required for any new AI agent to correctly locate the data repo and access necessary secrets.

## Steps
1.  **Execute Script**: Run `python3 scripts/setup_env.py` in the terminal.
2.  **Follow Prompts**: Enter your `AGENT_DATA_ROOT`, `GITHUB_TOKEN`, and other required keys.
3.  **Verification**: After setup, run `/status` to ensure connectivity to the data layer.

> [!IMPORTANT]
> This command should be run once after cloning the repository or whenever your path/token information changes.
