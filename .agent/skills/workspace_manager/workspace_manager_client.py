import os
import re
import subprocess

class WorkspaceManager:
    def __init__(self, workspace_root):
        self.root = workspace_root
        self.projects_dir = os.path.join(self.root, "projects")
        self.dashboard_path = os.path.join(self.root, "DASHBOARD.md")

    def get_active_projects(self):
        """解析 DASHBOARD.md 表格，提取專案名稱與 Git 連結"""
        projects = []
        if not os.path.exists(self.dashboard_path):
            return projects

        with open(self.dashboard_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # 尋找表格行：| Type | Project Name | Link | Status |
        # 範例：| 🎨 | **Beauty-PK** | [Repo](https://github.com/alstonhuang/beauty-pk) | ✅ Active |
        for line in lines:
            match = re.search(r"\|\s*.*?\s*\|\s*\*\*?(.*?)\*\*?\s*\|\s*\[Repo\]\((.*?)\)\s*\|", line)
            if match:
                name = match.group(1).strip()
                repo_url = match.group(2).strip()
                projects.append({"name": name, "url": repo_url})
        return projects

    def sync_all_projects(self):
        """批量克隆所有專案"""
        projects = self.get_active_projects()
        results = []
        
        if not os.path.exists(self.projects_dir):
            os.makedirs(self.projects_dir)

        for p in projects:
            target_path = os.path.join(self.projects_dir, p['name'])
            if os.path.exists(target_path):
                results.append(f"⏩ {p['name']} 已存在，跳過。")
                continue
            
            print(f"กำลังดึง數據 {p['name']}...") # 這裡是測試訊息
            try:
                subprocess.run(["git", "clone", p['url'], target_path], check=True)
                results.append(f"✅ {p['name']} 複製成功。")
            except Exception as e:
                results.append(f"❌ {p['name']} 複製失敗: {str(e)}")
        
        return results

if __name__ == "__main__":
    # 簡單測試
    mgr = WorkspaceManager(".")
    print("偵測到的專案:", mgr.get_active_projects())
