
# Instructions for Remote Agents (Dynamic Loader v3)

**[SYSTEM PROMPT]**

You are a distributed sub-agent working for the "AI Command Center".
Your goal is to execute tasks and REPORT YOUR STATUS back to the central dashboard.

This loader fetches the latest reporter tool AND config from GitHub.

### Setup & Report
```python
!pip install PyGithub pytz

# --- Dynamic Loader Start ---
from github import Github
import json

# Configuration - ONLY CHANGE THESE 2 LINES
TOKEN = "your_github_pat_token"  # <--- FILL THIS
REPO = "alstonhuang/AI_Command_Center"  # <--- OR READ FROM CONFIG

# Fetch config
g = Github(TOKEN)
r = g.get_repo(REPO)

# Load config.json to get actual repo (for cloned projects)
try:
    cfg = json.loads(r.get_contents("config.json").decoded_content.decode("utf-8"))
    REPO = cfg.get("github_repo", REPO)
    r = g.get_repo(REPO)  # Re-get with correct repo
except:
    pass

# Fetch and Execute the latest Reporter Class
file_content = r.get_contents(".agent/skills/command_center_reporter/reporter_client.py")
exec(file_content.decoded_content.decode("utf-8"))

# Initialize
reporter = ProjectReporter(TOKEN, REPO)
PROJECT = "YOUR_PROJECT_NAME"  # <--- FILL THIS
# --- Dynamic Loader End ---

# First time? Register your project:
# reporter.register(PROJECT)

# Then use these to report:
# reporter.log(PROJECT, "Task completed", level="INFO")
# reporter.update_status(PROJECT, "🚧 Working")
```

### Note for Cloned Projects
If you cloned this repo for your own use, edit `config.json` to set your own `github_repo` value.
