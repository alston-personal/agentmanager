---
name: command_center_reporter
description: Enables remote AI agents (Colab, ChatGPT) to update the central Dashboard via GitHub API.
---

# Command Center Reporter

This skill provides the improved workflow for "Distributed Agent Management".
It allows external AI sessions to report back to the `DASHBOARD.md`.

## Resources
- **Client Code**: `reporter_client.py` (The actual Python logic)
- **Prompt**: `INSTRUCTION_PROMPT.md` (The text user should copy-paste to other agents)

## How to use
When the user wants to connect a remote AI (like a Colab notebook) to the Command Center:
1.  **Read** the `INSTRUCTION_PROMPT.md`.
2.  **Display** the content to the user (or copy it to clipboard if supported).
3.  Instruct the user to:
    - Generate a GitHub Personal Access Token (PAT) with `repo` scope.
    - Paste the prompt and the Token into the remote AI session.

## Maintenance
If the `DASHBOARD.md` structure changes, update `reporter_client.py` parsing logic accordingly.
