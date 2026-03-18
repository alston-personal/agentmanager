import os
import re
import subprocess
import json

class WorkspaceManager:
    def __init__(self, workspace_root, org_name="alston-personal"):
        self.root = os.path.abspath(workspace_root)
        self.projects_dir = os.path.join(self.root, "projects")
        self.workspace_link_dir = os.path.join(self.root, "workspace")
        self.physical_root = "/home/ubuntu"
        self.dashboard_path = os.path.join(self.root, "DASHBOARD.md")
        self.org_name = org_name
        self.token_path = os.path.join(self.root, ".gh_token")

    def _get_token(self):
        if os.path.exists(self.token_path):
            with open(self.token_path, "r") as f:
                return f.read().strip()
        return os.environ.get("GITHUB_TOKEN")

    def list_org_repos(self):
        """獲取 Organization 下的所有 Repos"""
        token = self._get_token()
        env = os.environ.copy()
        if token:
            env["GITHUB_TOKEN"] = token
        
        try:
            result = subprocess.run(
                ["gh", "api", f"/orgs/{self.org_name}/repos", "--jq", '.[] | {name: .name, url: .ssh_url}'],
                capture_output=True, text=True, env=env
            )
            # 解析每行 JSON
            repos = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    repos.append(json.loads(line))
            return repos
        except Exception as e:
            print(f"❌ 無法獲取 Org 專案: {e}")
            return []

    def relink_workspace(self):
        """重新整理 workspace/ 下的 Symlinks，確保指向 /home/ubuntu/ 下的實體資料夾"""
        if not os.path.exists(self.workspace_link_dir):
            os.makedirs(self.workspace_link_dir)
        
        results = []
        for item in os.listdir(self.physical_root):
            physical_path = os.path.join(self.physical_root, item)
            if os.path.isdir(physical_path) and item not in ["agentmanager", "projects", "workspace"]:
                if item.startswith("."): continue
                
                link_path = os.path.join(self.workspace_link_dir, item.lower())
                if os.path.exists(link_path) or os.path.islink(link_path):
                    os.remove(link_path)
                
                os.symlink(physical_path, link_path)
                results.append(f"🔗 Linked {item.lower()} -> {physical_path}")
        return results

    def migrate_project_to_org(self, project_name):
        """將本地專案 push 到 Organization (如果尚未在 Org 下)"""
        token = self._get_token()
        local_path = os.path.join(self.physical_root, project_name)
        if not os.path.exists(local_path):
            return f"❌ 找不到本地路徑: {local_path}"

        env = os.environ.copy()
        if token: env["GITHUB_TOKEN"] = token

        try:
            # 1. 在 Org 建立 Repo (如果已存在會跳過或報錯)
            subprocess.run(["gh", "repo", "create", f"{self.org_name}/{project_name}", "--private"], env=env)
            
            # 2. 獲取當前分支名稱 (master 或 main)
            branch_result = subprocess.run(["git", "-C", local_path, "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
            current_branch = branch_result.stdout.strip() or "master"

            # 3. 修改或新增 Remote
            # 使用 HTTPS URL 以避免 SSH fingerprint 提示，並利用 token 認證
            new_url = f"https://x-access-token:{token}@github.com/{self.org_name}/{project_name}.git"
            check_remote = subprocess.run(["git", "-C", local_path, "remote", "get-url", "origin"], capture_output=True)
            
            if check_remote.returncode == 0:
                subprocess.run(["git", "-C", local_path, "remote", "set-url", "origin", new_url], env=env)
            else:
                subprocess.run(["git", "-C", local_path, "remote", "add", "origin", new_url], env=env)
            
            # 4. Push
            subprocess.run(["git", "-C", local_path, "push", "-u", "origin", current_branch], env=env)
            return f"✅ {project_name} 已成功遷移至 {self.org_name} (Branch: {current_branch})"
        except Exception as e:
            return f"❌ 遷移 {project_name} 失敗: {e}"

    def update_dashboard_from_org(self):
        """根據 Org 的內容同步更新 DASHBOARD.md"""
        repos = self.list_org_repos()
        # 這裡的邏輯可以更複雜，例如檢查目前的表格並 append 新內容
        # 暫時回傳列表供 Agent 參考
        return repos

if __name__ == "__main__":
    import sys
    mgr = WorkspaceManager("/home/ubuntu/agentmanager")
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "relink":
            for r in mgr.relink_workspace(): print(r)
        elif cmd == "org-list":
            for p in mgr.list_org_repos(): print(f"- {p['name']}: {p['url']}")
        elif cmd == "migrate" and len(sys.argv) > 2:
            print(mgr.migrate_project_to_org(sys.argv[2]))
