---
description: Report current project status to AI Command Center
---

# /report - Report Status to Command Center

Use this command to report your current work status back to the AI Command Center.

## Prerequisites
- This workspace must have the `command_center_reporter` skill installed

## Steps

### 1. Identify Current Project
Use the current workspace folder name as the project name.
Example: If workspace is `Beauty-PK`, project name is `Beauty-PK`.

### 2. Check for Existing Token
Look for token in this priority:
1. Environment variable `GH_TOKEN`
2. File `.gh_token` in workspace root (gitignored)
3. Ask user ONCE and offer to save it

If no token exists, ask:
> "I need a GitHub Token to report to the Command Center. Please provide your token. (I can save it locally so you don't need to enter it again)"

If user provides token, save to `.gh_token` file (and ensure it's in .gitignore).

### 3. Load and Execute Reporter
```python
import os

# Load token from file or environment
token_file = ".gh_token"
if os.path.exists(token_file):
    with open(token_file) as f:
        TOKEN = f.read().strip()
else:
    TOKEN = os.environ.get("GH_TOKEN")

REPO = "alstonhuang/AI_Command_Center"  # Read from config.json if exists

# Dynamic load reporter
from github import Github
g = Github(TOKEN)
r = g.get_repo(REPO)
exec(r.get_contents(".agent/skills/command_center_reporter/reporter_client.py").decoded_content.decode("utf-8"))

reporter = ProjectReporter(TOKEN, REPO)
PROJECT = "Beauty-PK"  # Use workspace name
```

### 4. Auto-Register if Needed
Before logging, check if project exists. If not, auto-register:
```python
# This will create Dashboard entry + STATUS.md if they don't exist
reporter.register(PROJECT, project_type="🖥️", link="(Local Workspace)")
```

### 5. Parse User Input
- If user said `/report Completed feature X`:
  - Log: `reporter.log(PROJECT, "Completed feature X", level="INFO")`
  
- If user said `/report`:
  - Summarize recent work based on conversation context
  - Ask for confirmation: "I'll report: '[summary]'. OK?"
  - Then log it

### 6. Confirm Success
Tell user: "✅ Reported to AI Command Center!"

## ⚠️ IMPORTANT
- **DO NOT** use `git clone` to update the Command Center
- **ALWAYS** use the GitHub API via `reporter.log()` and `reporter.update_status()`
- This is faster, cleaner, and avoids merge conflicts
