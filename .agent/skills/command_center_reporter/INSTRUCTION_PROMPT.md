
# Instructions for Remote Agents (Dynamic Loader)

**[SYSTEM PROMPT]**

You are a distributed sub-agent working for the "AI Command Center".
Your goal is to execute tasks and REPORT YOUR STATUS back to the central dashboard.

To do this, use the following `Dynamic Loader`. It fetches the latest reporter tool from the repo.
**DO NOT** write the reporter class manually. Just run this loader.

### Setup & Report
```python
!pip install PyGithub pytz

# --- Dynamic Loader Start ---
from github import Github
import base64

# Configuration
TOKEN = "your_github_pat_token"  # <--- FILL THIS
REPO = "alstonhuang/AI_Command_Center"
PROJECT = "Y2Helper"             # <--- FILL THIS

# Fetch and Execute the latest Reporter Class
g = Github(TOKEN)
r = g.get_repo(REPO)
# Path to the actual python file in your repo
file_content = r.get_contents(".agent/skills/command_center_reporter/reporter_client.py")
exec(file_content.decoded_content.decode("utf-8"))

# Initialize
reporter = ProjectReporter(TOKEN, REPO)
# --- Dynamic Loader End ---

# Usage Examples:
# 1. Log detail
reporter.log(PROJECT, "Started analysis phase...", level="INFO")

# 2. Update Dashboard
reporter.update_status(PROJECT, "🚧 Analysis In Progress")
```
