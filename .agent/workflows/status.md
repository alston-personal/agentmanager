---
description: Show current status of all AI projects in the Command Center
---

# /status - View AI Command Center Status

Execute these steps to show the current project status:

## Steps

1. **Pull latest changes from GitHub**
   ```powershell
   git pull origin main
   ```

2. **Display Dashboard summary**
   Read and display `DASHBOARD.md` content.

3. **List all projects with detailed status**
   For each folder in `projects/`, read its `STATUS.md` and summarize:
   - Last Status
   - Recent Activity Log entries (top 3)
   - Any Blockers

4. **Present results in a formatted table**
   Show the user:
   - Dashboard overview (all projects with status icons)
   - Per-project details (if STATUS.md exists)
   - Pending actions or warnings
