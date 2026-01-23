---
name: command_center_reporter
description: Enables remote AI agents (Colab, ChatGPT) to update the central Dashboard via GitHub API.
---

# Command Center Reporter Skill

This skill enables you to report your work status back to the central "AI Command Center".

## 🎯 Purpose
- Report progress, errors, and blockers to a central dashboard
- Keep the human operator informed across all AI projects

## 📋 Prerequisites
Before using this skill, ensure:
1. You have the GitHub Token (ask the user if needed, stored in environment or provided directly)
2. You know the project name you're working on

## 🚀 How to Use (Standard Procedure)

### Step 1: Setup (First time only)
Run this Python code to load the reporter:

```python
!pip install PyGithub pytz

from github import Github
import json

# Get these from the user or environment
TOKEN = "github_pat_token"  # Ask user for this
REPO = "alstonhuang/AI_Command_Center"  # Or read from config

# Dynamic load the reporter class
g = Github(TOKEN)
r = g.get_repo(REPO)
file_content = r.get_contents(".agent/skills/command_center_reporter/reporter_client.py")
exec(file_content.decoded_content.decode("utf-8"))

reporter = ProjectReporter(TOKEN, REPO)
```

### Step 2: Register (If this is a new project)
```python
reporter.register("YourProjectName")
```
This will:
- Add a row to DASHBOARD.md
- Create projects/YourProjectName/STATUS.md

### Step 3: Report Progress (During work)
```python
# Log detailed activity
reporter.log("YourProjectName", "Completed data processing step 1", level="INFO")

# Update dashboard status
reporter.update_status("YourProjectName", "🚧 Processing (50%)")
```

### Log Levels
- `INFO` - Normal progress
- `WARN` - Encountered issue but continuing
- `DONE` - Task completed

## ⚠️ Important Notes
- **DO NOT** clone the AI_Command_Center repo to temp
- **DO** use the GitHub API method above (it's faster and cleaner)
- All writes go directly to GitHub via API, no local files needed

## 🔧 For Local Antigravity Workspaces
If you're in a local VS Code workspace (not Colab):
1. This skill folder should be symlinked from the master at `d:\AgentManager\.agent\skills\command_center_reporter`
2. You can still use the same Python code above to report
3. Or simply tell the user what to update and let them sync manually

## 📁 File Locations
- Dashboard: `DASHBOARD.md` (main status board)
- Project logs: `projects/{ProjectName}/STATUS.md`
- Config: `config.json` (contains repo name for cloned instances)
