---
name: command_center_reporter
description: Enables AI agents to report status to the central AI Command Center via GitHub API.
---

# Command Center Reporter Skill

## 🚨🚨🚨 CRITICAL: DO NOT USE GIT CLONE 🚨🚨🚨

**NEVER do this:**
```
❌ git clone https://github.com/.../AI_Command_Center.git /tmp/...
❌ cd /tmp/AI_Command_Center && git add . && git commit && git push
```

**ALWAYS do this:**
```python
✅ reporter.log("ProjectName", "Message")
✅ reporter.update_status("ProjectName", "Status")
```

The GitHub API method is:
- Faster (no clone/pull needed)
- Cleaner (no temp files)
- Conflict-free (atomic operations)

---

## 🎯 Purpose
Report your work status back to the central "AI Command Center" dashboard.

## 📋 Standard Operating Procedure

### Step 1: One-time Setup
```python
!pip install PyGithub pytz

from github import Github

# Get token from user or .gh_token file
TOKEN = "user_provides_this"
REPO = "alstonhuang/AI_Command_Center"

# Dynamic load the reporter (ALWAYS fetch latest from GitHub!)
g = Github(TOKEN)
r = g.get_repo(REPO)
code = r.get_contents(".agent/skills/command_center_reporter/reporter_client.py")
exec(code.decoded_content.decode("utf-8"))

reporter = ProjectReporter(TOKEN, REPO)
```

### Step 2: Register (First time for new project)
```python
reporter.register("YourProjectName")
```

### Step 3: Report (Every time you have progress)
```python
# Log detailed activity
reporter.log("YourProjectName", "Completed feature X", level="INFO")

# Update dashboard status (only when phase changes)
reporter.update_status("YourProjectName", "🚧 Working")
```

---

## 🔄 For /cc-report Command (Namespaced)
When user says `/cc-report` or `/report` (legacy alias):
1. Auto-summarize your work in this session
2. Fetch previous STATUS.md to see what was already reported
3. Report only NEW accomplishments
4. DO NOT ask user what to report - figure it out yourself!

---

## ⚠️ Common Mistakes to Avoid

| ❌ Wrong | ✅ Correct |
| :--- | :--- |
| `git clone` the Command Center | Use `reporter.log()` API |
| Ask user "what do you want to report?" | Auto-summarize from conversation |
| Report everything every time | Read previous log, report only new items |
| Create temp folders | No local files needed |

---

## 📁 File Locations (on GitHub, not local!)
- Dashboard: `DASHBOARD.md`
- Project logs: `projects/{ProjectName}/STATUS.md`
- Config: `config.json`
