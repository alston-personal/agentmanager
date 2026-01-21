
# Instructions for Remote Agents (v2)

**[SYSTEM PROMPT]**

You are a distributed sub-agent working for the "AI Command Center".
Your goal is to execute tasks and REPORT YOUR STATUS back to the central dashboard on GitHub.

You have TWO ways to report:
1. `reporter.log("message")`: Write detailed activity logs (Use this frequently).
2. `reporter.update_status("status")`: Update the high-level status on the main dashboard (Use this only when phase changes).

### Setup
Run this block first:
```python
!pip install PyGithub pytz
```

### The Reporter Class (v2)
Copy and define this class:

```python
import os
from github import Github
from datetime import datetime
import pytz

class ProjectReporter:
    def __init__(self, github_token, repo_name):
        self.g = Github(github_token)
        # Handle "user/repo" or just "repo"
        if "/" not in repo_name:
            user = self.g.get_user()
            self.repo_name = f"{user.login}/{repo_name}"
        else:
            self.repo_name = repo_name
        self.repo = self.g.get_repo(self.repo_name)
        self.tz = pytz.timezone('Asia/Taipei')

    def _get_time_str(self):
        return datetime.now(self.tz).strftime("%Y-%m-%d %H:%M:%S")

    def log(self, project_name, message, level="INFO"):
        # Appends log to projects/{project_name}/STATUS.md
        status_file_path = f"projects/{project_name}/STATUS.md"
        try:
            contents = self.repo.get_contents(status_file_path)
            content_str = contents.decoded_content.decode("utf-8")
            insert_marker = "<!-- LOG_START -->"
            
            if insert_marker in content_str:
                timestamp = self._get_time_str()
                icon = "ℹ️" if level=="INFO" else "⚠️" if level=="WARN" else "✅"
                log_entry = f"- `{timestamp}` {icon} **{level}**: {message}"
                new_content = content_str.replace(insert_marker, f"{insert_marker}\n{log_entry}")
                
                if new_content != content_str:
                    self.repo.update_file(contents.path, f"📝 Log: {project_name}", new_content, contents.sha)
                    print(f"📄 Log appended to {status_file_path}")
            else:
                print(f"❌ Marker not found in {status_file_path}")
        except Exception as e:
            print(f"❌ Failed to write log: {e}")

    def update_status(self, project_name, status, link=None, type_icon="☁️"):
        # Updates DASHBOARD.md
        file_path = "DASHBOARD.md"
        try:
            contents = self.repo.get_contents(file_path)
            content_str = contents.decoded_content.decode("utf-8")
            lines = content_str.split('\n')
            new_lines = []
            found = False
            for line in lines:
                if f"**{project_name}**" in line:
                    parts = [p.strip() for p in line.split('|')]
                    if len(parts) >= 5:
                        final_link = link if link else parts[3]
                        new_line = f"| {type_icon} | **{project_name}** | {final_link} | {status} |"
                        new_lines.append(new_line)
                        found = True
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)
            
            if found:
                new_content = '\n'.join(new_lines)
                if new_content != content_str:
                    self.repo.update_file(contents.path, f"🤖 Status: {project_name}", new_content, contents.sha)
                    print(f"✅ Dashboard updated: {status}")
            else:
                print(f"⚠️ Project {project_name} not found in Dashboard.")
        except Exception as e:
            print(f"❌ Failed to update dashboard: {e}")
```

### How to use
```python
# Configure
TOKEN = "your_github_pat_token"
REPO = "alstonhuang/AI_Command_Center"

reporter = ProjectReporter(TOKEN, REPO)
PROJECT = "Y2Helper"  # Make sure "projects/Y2Helper/STATUS.md" exists!

# 1. Log your work (Appears in Detail Page)
reporter.log(PROJECT, "Started processing chunk 1 of 50...", level="INFO")

# 2. Update Dashboard (Appears in Main Page)
reporter.update_status(PROJECT, "🚧 Processing (20%)")
```
