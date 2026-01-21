
"""
AI Command Center - Remote Reporter Client
此程式碼設計用於 Google Colab 或其他遠端 Python 環境。
它允許遠端 AI 代理自動更新 Command Center 的 DASHBOARD.md。

Usage:
1. 安裝依賴: !pip install PyGithub
2. 初始化: reporter = CommandCenterReporter("YOUR_GITHUB_TOKEN", "YOUR_REPO_NAME")
3. 更新: reporter.update_status("Project Name", "New Status", "Next Action")
"""

import os
from github import Github
from datetime import datetime
import re

class ProjectReporter:
    def __init__(self, github_token, repo_name="AI_Command_Center"):
        """
        初始化回報器
        :param github_token: GitHub Personal Access Token
        :param repo_name: 您的 Repository 名稱 (e.g., 'username/AI_Command_Center')
        """
        self.g = Github(github_token)
        # 自動搜尋 user 的 repo
        try:
            self.user = self.g.get_user()
            # 如果輸入只是 "AI_Command_Center", 自動加上 username
            if "/" not in repo_name:
                self.repo_name = f"{self.user.login}/{repo_name}"
            else:
                self.repo_name = repo_name
            
            self.repo = self.g.get_repo(self.repo_name)
            print(f"✅ Connected to Command Center: {self.repo_name}")
        except Exception as e:
            print(f"❌ Connection Failed: {e}")
            raise

    def update_status(self, project_name, status, link=None, type_icon="☁️"):
        """
        更新 Dashboard 上的專案狀態
        """
        file_path = "DASHBOARD.md"
        try:
            # 1. 取得目前檔案內容
            contents = self.repo.get_contents(file_path)
            content_str = contents.decoded_content.decode("utf-8")
            
            # 2. 解析並更新表格
            # 尋找目標行
            lines = content_str.split('\n')
            new_lines = []
            found = False
            
            # 構建新的表格行格式: | Type | **Name** | Link | Status |
            # 如果沒有 Link，就嘗試保留原本的，或使用預設
            
            for line in lines:
                if f"**{project_name}**" in line:
                    # 找到既有專案，更新它
                    parts = [p.strip() for p in line.split('|')]
                    # parts[0] is empty (before first |), parts[1] is Type, parts[2] is Name, parts[3] is Link, parts[4] is Status
                    
                    if len(parts) >= 5:
                        current_link = parts[3]
                        # 如果有提供新連結就用新的，否則保留舊的
                        final_link = link if link else current_link
                        
                        # 更新行
                        new_line = f"| {type_icon} | **{project_name}** | {final_link} | {status} |"
                        new_lines.append(new_line)
                        found = True
                        print(f"📝 Updating existing project: {project_name} -> {status}")
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)
            
            # 如果沒找到，則新增到表格最後 (這比較複雜，要找表格結尾，暫時簡化為 append 到特定區塊後)
            # 為了簡單起見，如果沒找到，我們建議使用者先手動加一次，或者我們把它插在表格最後一行
            if not found:
                print(f"⚠️ Project '{project_name}' not found in Dashboard. Appending is complex via API, skipping auto-add to avoid breaking format.")
                # TODO: Implement smart insertion logic
                return

            # 3. 推送更新
            new_content = '\n'.join(new_lines)
            if new_content != content_str:
                commit_message = f"🤖 Bot: Update status for {project_name}"
                self.repo.update_file(contents.path, commit_message, new_content, contents.sha)
                print(f"🚀 Status pushed to GitHub successfully!")
            else:
                print("No changes needed.")

        except Exception as e:
            print(f"❌ Error updating dashboard: {e}")
