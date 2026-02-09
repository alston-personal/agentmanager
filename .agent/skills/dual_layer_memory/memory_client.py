
"""
Memory Sync Client
用於同步本地 memory/ 資料夾與 Private Data Repo。
"""
import os
import sys
from github import Github

def sync_memory(action):
    # 1. Get Config
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        try:
            with open(".gh_token", "r") as f:
                token = f.read().strip()
        except:
            print("❌ GITHUB_TOKEN not found.")
            return

    repo_name = os.environ.get("PRIVATE_DATA_REPO")
    if not repo_name:
        print("❌ PRIVATE_DATA_REPO not set in environment.")
        return

    g = Github(token)
    repo = g.get_repo(repo_name)
    
    files_to_sync = ["SHORT_TERM.md", "LONG_TERM.md"]
    local_dir = "memory"
    
    if not os.path.exists(local_dir):
        os.makedirs(local_dir)

    # 2. Execute Action
    if action == "pull":
        print(f"📥 Pulling memory from {repo_name}...")
        for filename in files_to_sync:
            try:
                remote_path = f"memory/{filename}"
                content = repo.get_contents(remote_path).decoded_content.decode("utf-8")
                
                local_path = os.path.join(local_dir, filename)
                with open(local_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"✅ Extracted: {filename}")
            except Exception as e:
                print(f"⚠️ Could not pull {filename} (maybe new repo?): {e}")

    elif action == "push":
        print(f"📤 Pushing memory to {repo_name}...")
        for filename in files_to_sync:
            local_path = os.path.join(local_dir, filename)
            if os.path.exists(local_path):
                with open(local_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                remote_path = f"memory/{filename}"
                try:
                    # Try to update existing file
                    remote_file = repo.get_contents(remote_path)
                    if remote_file.decoded_content.decode("utf-8") != content:
                        repo.update_file(remote_path, f"🧠 Memory Update: {filename}", content, remote_file.sha)
                        print(f"✅ Updated: {filename}")
                    else:
                        print(f"⏹️ No changes: {filename}")
                except:
                    # File doesn't exist, create it
                    repo.create_file(remote_path, f"🧠 Memory Init: {filename}", content)
                    print(f"✅ Created: {filename}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python memory_client.py [pull|push]")
    else:
        sync_memory(sys.argv[1])
