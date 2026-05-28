#!/usr/bin/env python3
"""
Antigravity Context Handover Utility
Generates a highly compressed and context-rich "Handoff Capsule" (交接密碼封包)
from STATUS.md, dual-layer memories, and recent Git commits.
Helps local Continue (Gemma) or other LLMs enter the coding context in 1 second.
"""
import os
import sys
import subprocess
from pathlib import Path

def get_git_info(logic_dir: Path):
    git_logs = "無 Git 紀錄或非 Git 目錄"
    uncommitted = "無未提交的變更 (乾淨工作區)"
    
    try:
        # 1. 取得最近 3 次的 Commit 紀錄
        cmd_log = "git log -n 3 --pretty=format:'- %h: %s (%an)'"
        res_log = subprocess.run(cmd_log, shell=True, cwd=str(logic_dir), capture_output=True, text=True, timeout=5)
        if res_log.returncode == 0 and res_log.stdout.strip():
            git_logs = res_log.stdout.strip()
            
        # 2. 取得當前工作區未提交的檔案狀態 (git status -s)
        cmd_status = "git status -s"
        res_status = subprocess.run(cmd_status, shell=True, cwd=str(logic_dir), capture_output=True, text=True, timeout=5)
        if res_status.returncode == 0 and res_status.stdout.strip():
            status_summary = res_status.stdout.strip()
            
            # 3. 取得當前修改的具體行數與統計 (git diff)
            cmd_diff = "git diff --stat"
            res_diff = subprocess.run(cmd_diff, shell=True, cwd=str(logic_dir), capture_output=True, text=True, timeout=5)
            diff_stat = res_diff.stdout.strip() if res_diff.returncode == 0 and res_diff.stdout.strip() else ""
            
            uncommitted = f"偵測到未提交的異動檔案：\n```text\n{status_summary}\n```"
            if diff_stat:
                uncommitted += f"\n變更行數統計：\n```text\n{diff_stat}\n```"
                
    except Exception as e:
        git_logs = f"獲取 Git 資訊失敗: {e}"
        
    return git_logs, uncommitted

def generate_capsule(proj_dir: Path):
    proj_name = proj_dir.name
    status_file = proj_dir / "STATUS.md"
    short_term_file = proj_dir / "memory" / "SHORT_TERM.md"
    long_term_file = proj_dir / "memory" / "LONG_TERM.md"
    
    # 讀取 STATUS.md 中的未完成任務
    todo_list = []
    if status_file.exists():
        try:
            content = status_file.read_text(encoding="utf-8")
            for line in content.splitlines():
                if "- [ ]" in line or "- [/]" in line:
                    todo_list.append(line.strip())
        except Exception as e:
            todo_list.append(f"讀取 STATUS.md 失敗: {e}")
    else:
        todo_list.append("找不到 STATUS.md")
        
    # 讀取短期記憶焦點
    focus = "無短期記憶"
    if short_term_file.exists():
        try:
            content = short_term_file.read_text(encoding="utf-8")
            lines = [l.strip() for l in content.splitlines() if l.strip()]
            focus = "\n".join(lines[:12])
        except Exception as e:
            focus = f"讀取短期記憶失敗: {e}"
            
    # 讀取長期記憶規則
    rules = "無長期記憶"
    if long_term_file.exists():
        try:
            content = long_term_file.read_text(encoding="utf-8")
            lines = [l.strip() for l in content.splitlines() if l.strip()]
            rules = "\n".join(lines[:8])
        except Exception as e:
            rules = f"讀取長期記憶失敗: {e}"
            
    git_logs, uncommitted = get_git_info(proj_dir)
    
    capsule = f"""==================== 📦 AGENTOS CONTEXT HANDOVER CAPSULE ====================
【專案交接密碼封包】請直接複製以下內容並貼給您的新 AI 助理 (例如 Continue 或 Codex)

你現在接手專案 '{proj_name}' 的開發工作。請「不要猜測」，嚴格依據以下最新的記憶與焦點前進：

1. 🎯 當前開發焦點 (SHORT_TERM):
{focus}

2. 📋 待辦任務清單 (STATUS):
{chr(10).join(todo_list[:10]) if todo_list else "- 無待辦項目"}

3. ⚠️ 當前工作區「未提交的變更」 (Uncommitted Changes - 最關鍵的斷點):
{uncommitted}

4. 🛠️ 近期已提交變更歷史 (Git Log):
{git_logs}

5. 🔒 專案核心限制與規則 (LONG_TERM):
{rules}

============================================================================
請遵循上述焦點與規則，並隨時閱讀當前工作區檔案以延續開發進度。
"""
    return capsule

def main():
    # 預設為當前執行目錄
    curr_dir = Path.cwd()
    
    # 檢查是否有 memory/ 或是 STATUS.md，如果沒有，嘗試往上找或回報
    if not (curr_dir / "STATUS.md").exists() and not (curr_dir / "memory").exists():
        # 嘗試檢查是否在子目錄，往上尋找一層
        if (curr_dir.parent / "STATUS.md").exists():
            curr_dir = curr_dir.parent
        else:
            print(f"⚠️ 警告: 當前目錄 '{curr_dir}' 未偵測到 STATUS.md 或 memory/ 記憶層。")
            print("請於您的專案邏輯根目錄執行此腳本 (例如 /home/ubuntu/moltbot)")
            sys.exit(1)
            
    proj_name = curr_dir.name
    capsule = generate_capsule(curr_dir)
    print(capsule)
    
    # 自動備份至資料層 (Data Layer)
    data_layer_dir = Path("/home/ubuntu/agent-data/projects") / proj_name
    if data_layer_dir.exists():
        capsule_file = data_layer_dir / "handoff_capsule.md"
        try:
            capsule_file.write_text(capsule, encoding="utf-8")
            print(f"💾 [防中斷備份] 已成功將最新交接檔寫入資料層：\n   👉 {capsule_file}")
        except Exception as e:
            print(f"⚠️ 寫入資料層備份失敗: {e}")
    else:
        print(f"ℹ️ 未在資料層偵測到對應的專案目錄 '{data_layer_dir}'，跳過自動存檔。")
    
    # 嘗試複製到剪貼簿 (如果系統支援 xclip 且已安裝)
    try:
        process = subprocess.Popen(['xclip', '-selection', 'clipboard'], stdin=subprocess.PIPE, close_fds=True)
        process.communicate(input=capsule.encode('utf-8'))
        print("📋 [貼心提醒] 交接密碼封包已自動複製到您的系統剪貼簿！可直接貼上至對話框。")
    except Exception:
        pass

if __name__ == "__main__":
    main()
