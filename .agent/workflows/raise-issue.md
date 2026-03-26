---
description: Formalize a bug or rework task into the Agent OS Data Layer Issue Tracker.
---
# Issue Raising Workflow

This workflow translates unexpected behavior, style drift, or bugs into actionable JSON tickets in the Project's data layer (`agent-data/projects/.../issues/`).
This ensures non-blocking, asynchronous communication between agents and tracking over multiple sessions.

## Execution Steps

1. **Verify Project Exists**:
   Ensure the project folder exists in `/home/ubuntu/agent-data/projects/`.

2. **Run The CLI**:
   Run the `manage_issues.py` script to raise the issue. Provide a clear description and mark priority appropriately (high, medium, low).

   ```bash
   python3 /home/ubuntu/agentmanager/scripts/manage_issues.py raise <project_name> "<title>" "<detailed description>" --priority high --tags "bug,style_drift"
   ```

   *Note: Ensure you escape quotes correctly inside the command.*

3. **Verify Output**:
   Check if the tool successfully reports `✅ Issue ISSUE-XXXXXXXXXXXXXX successfully created`.

4. **Update Observers** (Optional):
   If this is an urgent blocker, you may notify other agents via the `INBOX` or use Signal interrupts if available in the project logic layer.

## When to use this:
- An Agent detects its predecessor generated low-quality output or hallucinated logic.
- A long-running command failed, and the Agent cannot fix it immediately in the current context.
- The User explicitly reports a bug or stylistic error (e.g., "The card looks wrong").

## Reference Commands:
- To list issues: `python3 /home/ubuntu/agentmanager/scripts/manage_issues.py list <project_name>`
- To resolve: `python3 /home/ubuntu/agentmanager/scripts/manage_issues.py resolve <project_name> <issue_id> "Resolution text"`
