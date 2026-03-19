#!/usr/bin/env python3
import os
import sys
from datetime import datetime, timezone

def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def read_file(path: str) -> str:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def main():
    project_root = os.getcwd()
    # 也可以透過環境變數傳遞
    agent_data_root = os.getenv("AGENT_DATA_ROOT", "/home/ubuntu/agent-data")
    sync_log_path = os.path.join(agent_data_root, "memory", "session_sync.md")
    
    # 找出專案名稱
    project_name = os.path.basename(project_root)
    if project_name == "agentmanager":
        # 如果在管理員路徑，可能需要更精確的識別
        # 這裡假設如果沒有指定專案，就是系統級任務
        pass

    short_term_path = os.path.join(project_root, "memory", "SHORT_TERM.md")
    short_term_content = read_file(short_term_path)
    
    # 提取關鍵任務
    tasks = []
    in_tasks = False
    for line in short_term_content.splitlines():
        if "## 🚧 Pending Tasks" in line or "## 近期任務" in line:
            in_tasks = True
            continue
        if in_tasks and line.startswith("- [ ]"):
            tasks.append(line.strip())
        elif in_tasks and line.startswith("##"):
            in_tasks = False

    # 生成交接摘要
    timestamp = utc_now()
    summary = [
        f"\n## 🤝 Context Handover @ {timestamp}",
        f"- **Project**: `{project_name}`",
        f"- **Status**: Concluded active session.",
        f"- **Key Pending Tasks**:",
    ]
    if tasks:
        summary.extend([f"  {t}" for t in tasks[:5]])
    else:
        summary.append("  - No critical pending tasks.")
    
    summary.append(f"- **Instruction for Next Agent**: Please resume from the above tasks in `{project_name}`.")
    summary.append("\n---\n")

    # 寫入全域同步日誌
    with open(sync_log_path, "a", encoding="utf-8") as f:
        f.write("\n".join(summary))
    
    print(f"✅ Handover summary appended to {sync_log_path}")

if __name__ == "__main__":
    main()
