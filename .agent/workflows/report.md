---
description: Report current project status to AI Command Center
---

# /report - Report Status to Command Center

Use this command to report your current work status back to the AI Command Center.

## Prerequisites
- This workspace must have the `command_center_reporter` skill installed (via symlink)
- User must provide GitHub token (or have it in environment)

## Steps

### 1. Identify Current Project
Determine the project name from:
- The current workspace folder name, OR
- Ask the user: "What is the project name for this workspace?"

### 2. Load Reporter (if not already loaded)
If you haven't loaded the reporter yet, execute this Python code:

```python
!pip install PyGithub pytz

from github import Github
import json

# Ask user for token if not available
TOKEN = input("GitHub Token: ") or os.environ.get("GH_TOKEN")
REPO = "alstonhuang/AI_Command_Center"

# Dynamic load
g = Github(TOKEN)
r = g.get_repo(REPO)
file_content = r.get_contents(".agent/skills/command_center_reporter/reporter_client.py")
exec(file_content.decoded_content.decode("utf-8"))

reporter = ProjectReporter(TOKEN, REPO)
```

### 3. Ask User What to Report
Ask the user:
> "What would you like to report?"
> - Progress update (what did you accomplish?)
> - Status change (new status like 🚧 Working, ✅ Done, ❌ Blocked?)
> - Blocker/Issue (what's blocking you?)

### 4. Execute Report
Based on user's response:

**For Progress Update:**
```python
reporter.log(PROJECT_NAME, "User's message here", level="INFO")
```

**For Status Change:**
```python
reporter.update_status(PROJECT_NAME, "New Status Icon + Text")
```

**For Blocker:**
```python
reporter.log(PROJECT_NAME, "BLOCKER: User's issue description", level="WARN")
reporter.update_status(PROJECT_NAME, "🛑 Blocked")
```

### 5. Confirm to User
Tell the user: "✅ Status reported to AI Command Center!"

## Quick Report (Non-Interactive)
If the user provides the message directly like `/report Completed data analysis`, skip the questions and just log it:
```python
reporter.log(PROJECT_NAME, "Completed data analysis", level="INFO")
```
