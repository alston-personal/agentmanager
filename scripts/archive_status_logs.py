#!/usr/bin/env python3
"""
scripts/archive_status_logs.py
==============================
自動掃描所有專案的 STATUS.md，若 Activity Log 超過 30 筆，
則保留最新的 15 筆，並將舊記錄歸檔至該專案的 memory/history/activity_archive.md 中。
"""
import re
import os
import sys
from pathlib import Path

HOME = Path("/home/ubuntu")
AGENT_DATA_ROOT = HOME / "agent-data"
PROJECTS_DIR = AGENT_DATA_ROOT / "projects"

def archive_project_status(proj_name: str, max_entries: int = 30, retain_entries: int = 15) -> bool:
    proj_dir = PROJECTS_DIR / proj_name
    status_md = proj_dir / "STATUS.md"
    if not status_md.exists():
        return False

    content = status_md.read_text(encoding="utf-8")
    
    # 尋找 <!-- LOG_START --> 與 <!-- LOG_END -->
    pattern = re.compile(r"(<!-- LOG_START -->)(.*?)(<!-- LOG_END -->)", re.DOTALL)
    match = pattern.search(content)
    if not match:
        return False
        
    start_tag, log_content, end_tag = match.groups()
    
    # 分割 log 行 (排除空行)
    log_lines = [line for line in log_content.splitlines() if line.strip()]
    if len(log_lines) <= max_entries:
        return False

    # 保留最前面的 retain_entries 筆（最新），歸檔後面的
    retained_lines = log_lines[:retain_entries]
    archived_lines = log_lines[retain_entries:]
    
    # 寫入歸檔檔案
    history_dir = proj_dir / "memory" / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    archive_file = history_dir / "activity_archive.md"
    
    archive_header = ""
    if not archive_file.exists():
        archive_header = f"# Activity Log Archive: {proj_name}\n\n"
        
    archive_content = archive_header + "\n".join(archived_lines) + "\n"
    
    # 追加寫入歸檔
    with open(archive_file, "a", encoding="utf-8") as f:
        f.write(archive_content)
        
    # 重建 STATUS.md
    new_log_content = "\n" + "\n".join(retained_lines) + "\n"
    new_content = content.replace(log_content, new_log_content, 1)
    status_md.write_text(new_content, encoding="utf-8")
    
    print(f"✨ [{proj_name}] 成功歸檔 {len(archived_lines)} 筆日誌，保留前 {len(retained_lines)} 筆。")
    return True

def main():
    if not PROJECTS_DIR.exists():
        print("❌ projects 目錄不存在")
        return 1
        
    print("🔍 開始掃描各專案 STATUS.md 進行日誌歸檔...")
    count = 0
    for d in PROJECTS_DIR.iterdir():
        if d.is_dir() and (d / "STATUS.md").exists():
            try:
                if archive_project_status(d.name):
                    count += 1
            except Exception as e:
                print(f"❌ 處理 {d.name} 時發生異常: {e}", file=sys.stderr)
                
    print(f"✅ 掃描完成。共優化了 {count} 個專案。")
    return 0

if __name__ == "__main__":
    sys.exit(main())
