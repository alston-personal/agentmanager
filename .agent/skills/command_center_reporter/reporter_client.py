
"""
AI Command Center - Advanced Reporter Client (v3)
支援寫入個別專案的 STATUS.md 日誌檔。
支援從 config.json 讀取設定。
"""

import os
import json
from github import Github
from datetime import datetime
import pytz # 需要 pip install pytz

def load_config_from_repo(github_token, repo_name):
    """
    從 GitHub repo 讀取 config.json
    """
    g = Github(github_token)
    repo = g.get_repo(repo_name)
    try:
        config_content = repo.get_contents("config.json")
        return json.loads(config_content.decoded_content.decode("utf-8"))
    except:
        return {"github_repo": repo_name, "timezone": "Asia/Taipei"}

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
        
        # 設定時區 (Taipei)
        self.tz = pytz.timezone('Asia/Taipei')

    def _get_time_str(self):
        return datetime.now(self.tz).strftime("%Y-%m-%d %H:%M:%S")

    def log(self, project_name, message, level="INFO"):
        """
        將詳細日誌寫入 projects/{project_name}/STATUS.md
        """
        status_file_path = f"projects/{project_name}/STATUS.md"
        
        try:
            contents = self.repo.get_contents(status_file_path)
            content_str = contents.decoded_content.decode("utf-8")
            
            # 使用標記 <!-- LOG_START --> 來定位插入點
            insert_marker = "<!-- LOG_START -->"
            
            if insert_marker in content_str:
                timestamp = self._get_time_str()
                icon = "ℹ️" if level=="INFO" else "⚠️" if level=="WARN" else "✅"
                log_entry = f"- `{timestamp}` {icon} **{level}**: {message}"
                
                # 在標記後插入新行 (最新的在最上面)
                new_content = content_str.replace(insert_marker, f"{insert_marker}\n{log_entry}")
                
                if new_content != content_str:
                    commit_msg = f"📝 Log: {project_name} - {message[:30]}..."
                    self.repo.update_file(contents.path, commit_msg, new_content, contents.sha)
                    print(f"📄 Log appended to {status_file_path}")
                else:
                    print("Log content identitical, skipping.")
            else:
                print(f"❌ Marker {insert_marker} not found in {status_file_path}. Please initialize the status file properly.")
                
        except Exception as e:
            print(f"❌ Failed to write log for {project_name}: {e}. (Does the file exist?)")

    def update_status(self, project_name, status, link=None, type_icon="☁️"):
        """
        更新 Dashboard 總表 (只更新狀態欄位)
        """
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
                        # Update row
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
                    self.repo.update_file(contents.path, f"🤖 Status Update: {project_name}", new_content, contents.sha)
                    print(f"✅ Dashboard updated: {project_name} -> {status}")
            else:
                print(f"⚠️ Project {project_name} not found in Dashboard. Use register() first.")
                
        except Exception as e:
            print(f"❌ Failed to update dashboard: {e}")

    def register(self, project_name, project_type="🖥️", link="(Local)", initial_status="🆕 Registered"):
        """
        自動註冊新專案：
        1. 在 Dashboard 新增一列
        2. 建立 projects/{project_name}/STATUS.md
        """
        # Step 1: Add to Dashboard
        file_path = "DASHBOARD.md"
        try:
            contents = self.repo.get_contents(file_path)
            content_str = contents.decoded_content.decode("utf-8")
            
            # Check if already exists
            if f"**{project_name}**" in content_str:
                print(f"ℹ️ Project {project_name} already exists in Dashboard.")
            else:
                # Find table end (line before ## Scratchpad or similar)
                lines = content_str.split('\n')
                insert_idx = None
                for i, line in enumerate(lines):
                    if line.startswith("## ") and "Scratchpad" in line:
                        insert_idx = i
                        break
                
                if insert_idx:
                    new_row = f"| {project_type} | **{project_name}** | {link} | {initial_status} |"
                    lines.insert(insert_idx, new_row)
                    new_content = '\n'.join(lines)
                    self.repo.update_file(contents.path, f"🆕 Register: {project_name}", new_content, contents.sha)
                    print(f"✅ Added {project_name} to Dashboard")
                else:
                    print("❌ Could not find insertion point in Dashboard")
                    
        except Exception as e:
            print(f"❌ Failed to register in Dashboard: {e}")
            return
        
        # Step 2: Create STATUS.md
        status_file_path = f"projects/{project_name}/STATUS.md"
        status_template = f"""# Project Status: {project_name}

## 📍 Summary
| Metric | Value |
| :--- | :--- |
| **Last Status** | {initial_status} |
| **Last Updated** | {self._get_time_str()} |

## 📝 Activity Log (Latest on Top)
<!-- LOG_START -->
- `{self._get_time_str()}` ✅ **INFO**: Project registered in AI Command Center
<!-- LOG_END -->

## 📅 Todo List
- [ ] Define objectives
- [ ] Implementation
- [ ] Review

## 🛑 Blockers & Issues
- None yet.
"""
        try:
            # Check if file exists
            self.repo.get_contents(status_file_path)
            print(f"ℹ️ STATUS.md already exists for {project_name}")
        except:
            # File doesn't exist, create it
            try:
                self.repo.create_file(status_file_path, f"🆕 Create STATUS for {project_name}", status_template)
                print(f"✅ Created {status_file_path}")
            except Exception as e:
                print(f"❌ Failed to create STATUS.md: {e}")
