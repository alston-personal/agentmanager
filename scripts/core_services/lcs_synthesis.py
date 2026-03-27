#!/usr/bin/env python3
import os
import shutil
import sys
import json
from datetime import datetime

# 核心路徑 (The Root of One)
ROOT_PATH = "/home/ubuntu/agentmanager"
CAPABILITIES_FILE = os.path.join(ROOT_PATH, ".agent/CAPABILITIES.md")
SKILLS_DIR = os.path.join(ROOT_PATH, ".agent/skills")

def log_synthesis(message):
    print(f"🧬 [LCS-Synthesis] {message}")

def promote_skill(source_path, skill_name, description, role_assigned):
    """
    將專案私有體驗 (Skill) 提煉併晉升到 AgentOS 主體 (Synthesis).
    """
    target_path = os.path.join(SKILLS_DIR, skill_name)
    
    # 建立技能結構
    os.makedirs(target_path, exist_ok=True)
    
    # 私有檔案拷貝 (如果是檔案) 或內容提煉
    if os.path.isfile(source_path):
        shutil.copy(source_path, os.path.join(target_path, os.path.basename(source_path)))
    
    # 自動更新萬神殿 (CAPABILITIES.md)
    with open(CAPABILITIES_FILE, "a") as f:
        f.write(f"| {skill_name} | `{skill_name}/` | {role_assigned} | ✅ 晉升 | {description} ({datetime.now().strftime('%Y-%m-%d')}) |\n")
    
    log_synthesis(f"子靈魂體驗 '{skill_name}' 已成功回饋並合一至 AgentOS。")

def main():
    if len(sys.argv) < 3:
        print("Usage: lcs-promote [source_path] [skill_name] [description] [role]")
        sys.exit(1)
        
    promote_skill(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else "虎掌")

if __name__ == "__main__":
    main()
