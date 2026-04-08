#!/usr/bin/env python3
import os
import re
import sys
import subprocess
import requests
from glob import glob
from datetime import datetime


PROJECT_ROOT = os.getenv("AGENT_PROJECT_ROOT", os.getcwd())
AGENT_DATA_ROOT = os.environ.get("AGENT_DATA_ROOT", os.path.expanduser("~/agent-data"))
CENTRAL_PROJECTS_DIR = os.path.join(AGENT_DATA_ROOT, "projects")
WORKFLOWS_DIR = os.path.join(PROJECT_ROOT, ".agent", "workflows")
SKILL_WORKFLOWS_DIR = os.path.join(PROJECT_ROOT, ".agent", "skills", "workflows")
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")


def load_env():
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    key, val = line.strip().split("=", 1)
                    os.environ[key] = val.strip('"').strip("'")


load_env()


def send_telegram_notification(text: str):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHANNEL_ID")
    if not token or not chat_id:
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            print(f"Telegram API Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Failed to send Telegram notification: {e}")


def parse_memory_brief():
    try:
        res = os.popen("free -g | grep Mem").read().strip().split()
        if len(res) >= 3:
            total = res[1]
            used = res[2]
            return f"{used}G / {total}G"
    except: pass
    return "N/A"


def format_telegram_report(uptime, memory, synced_count, expected_count, needs_update, project_rows):
    timestamp = datetime.now().strftime("%H:%M")
    lines = [
        f"🌐 *Agent OS: Ecosystem Pulse* ({timestamp})",
        "──────────────────────────",
        "🖥️ *System Health*",
        f" ├─ Uptime: {uptime}",
        f" ├─ Memory: {memory}",
        f" └─ Sync: `{synced_count}/{expected_count}` Projects",
        ""
    ]
    
    if needs_update:
        lines.append("⚠️ *Needs Attention (Stale)*")
        for p in needs_update[:5]: # Cap it to avoid long messages
            lines.append(f" └─ 🔴 *{p}* (Run `/report`)")
        if len(needs_update) > 5:
            lines.append(f" └─ ... and {len(needs_update)-5} more")
        lines.append("")
        
    lines.append("📂 *Project Matrix Status*")
    for row in project_rows:
        p_name = row['name']
        p_tag = row['tag']
        p_updated = row['updated']
        
        icon = "🟢" if "Verified" in p_tag else "🔴"
        # Extract MM/DD or just the end of the string
        date_part = "N/A"
        if p_updated and " " in p_updated:
            date_part = p_updated.split()[0][-5:].replace("-", "/")
        elif p_updated:
            date_part = p_updated.strip()[-5:]
            
        lines.append(f" {icon} {p_name} ({date_part})")
        
    return "\n".join(lines)


def normalize_workflow_name(raw_name: str) -> str:
    name = (raw_name or "").strip()
    if name.startswith("/"):
        name = name[1:]
    if name.startswith("workflow-"):
        name = name[len("workflow-"):]
    return name


def discover_workflows() -> list[str]:
    names = set()
    for folder in (WORKFLOWS_DIR, SKILL_WORKFLOWS_DIR):
        if not os.path.isdir(folder):
            continue
        for entry in os.listdir(folder):
            if entry.endswith(".md"):
                names.add(entry[:-3])
    return sorted(names)


def read_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def extract_summary_field(content: str, label: str) -> str:
    pattern = rf"\|\s*\*\*{re.escape(label)}\*\*\s*\|\s*([^|]+?)\s*\|"
    match = re.search(pattern, content)
    return match.group(1).strip() if match else ""


def extract_latest_log(content: str) -> str:
    for line in content.splitlines():
        if line.startswith("- "):
            return line[2:].strip()
    return ""


def run_status() -> str:
    """
    Generate project status table.
    Primary source: project.yaml (structured)
    Fallback: STATUS.md regex (legacy)
    """
    import sys
    import importlib.util

    # Try to use structured yaml source
    yaml_available = importlib.util.find_spec("yaml") is not None
    agent_core_path = os.path.join(PROJECT_ROOT, "agent_core")

    if yaml_available and os.path.isdir(agent_core_path):
        sys.path.insert(0, PROJECT_ROOT)
        try:
            from agent_core.project_store import list_projects
            projects = list_projects()
            if projects:
                # Sort by priority desc, then name
                projects.sort(key=lambda p: (-p.priority, p.name if hasattr(p, 'name') else p.project_id))
                lines = [
                    "| Project | Sector | Priority | Phase | Status | Health |",
                    "| :--- | :---: | :---: | :---: | :--- | :---: |",
                ]
                HEALTH_ICON = {"fresh": "🟢", "stale": "🟡", "unknown": "⚪"}
                for p in projects:
                    health_icon = HEALTH_ICON.get(p.health.freshness, "⚪")
                    lines.append(
                        f"| **{p.project_id}** | {p.sector} | P{p.priority} | {p.phase} | {p.status} | {health_icon} {p.health.freshness} |"
                    )
                lines.append("")
                lines.append(f"_Source: `project.yaml` — {len(projects)} projects_")
                return "\n".join(lines)
        except Exception as e:
            # Fall through to legacy method
            pass

    # Legacy fallback: regex parse STATUS.md
    status_paths = sorted(glob(os.path.join(CENTRAL_PROJECTS_DIR, "*", "STATUS.md")))
    if not status_paths:
        return f"No project status files found in {CENTRAL_PROJECTS_DIR}."

    rows = []
    for status_path in status_paths:
        project_name = os.path.basename(os.path.dirname(status_path))
        content = read_file(status_path)
        rows.append({
            "project": project_name,
            "status": extract_summary_field(content, "Last Status") or "N/A",
            "updated": extract_summary_field(content, "Last Updated") or "N/A",
            "activity": extract_latest_log(content) or "N/A",
        })

    lines = [
        "| Project | Last Status | Last Updated | Latest Activity |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['project']} | {row['status']} | {row['updated']} | {row['activity']} |"
        )
    lines.append("")
    lines.append("_Source: `STATUS.md` (legacy regex — upgrade to project.yaml for structured output)_")
    return "\n".join(lines)


def run_generic(workflow_name: str) -> str:
    if workflow_name == "register-project":
        if len(sys.argv) < 3:
            return "Usage: python3 scripts/run_workflow.py register-project <project-name> [--display-name ...]"
        register_script = os.path.join(PROJECT_ROOT, "scripts", "register_project.py")
        result = subprocess.run(
            ["python3", register_script, *sys.argv[2:]],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        return result.stdout.strip() if result.returncode == 0 else (result.stderr.strip() or "register-project failed")

    if workflow_name == "snapshot":
        snapshot_script = os.path.join(PROJECT_ROOT, "scripts", "create_snapshot.py")
        stream = os.popen(f"AGENT_DATA_ROOT='{AGENT_DATA_ROOT}' python3 '{snapshot_script}'")
        output = stream.read().strip()
        code = stream.close()
        if code is None:
            return f"Snapshot created: {output}"
        return f"Snapshot failed: {output or 'unknown error'}"

    workflow_paths = [
        os.path.join(WORKFLOWS_DIR, f"{workflow_name}.md"),
        os.path.join(SKILL_WORKFLOWS_DIR, f"{workflow_name}.md"),
    ]
    for workflow_path in workflow_paths:
        if os.path.exists(workflow_path):
            content = read_file(workflow_path)
            step_lines = [line.strip() for line in content.splitlines() if re.match(r"^\d+\.", line.strip())]
            response = [f"Workflow `/{workflow_name}` is loaded."]
            if step_lines:
                response.append("")
                response.append("Defined steps:")
                response.extend(step_lines)
            response.append("")
            response.append("Automatic execution is currently implemented for `/status`.")
            return "\n".join(response)
    available = ", ".join(f"/{name}" for name in discover_workflows()) or "(none)"
    return f"Unknown workflow: /{workflow_name}\nAvailable workflows: {available}"


def get_project_last_change(project_dir: str) -> float:
    """找出專案目錄中最後一個修改的檔案時間 (跳過 .git)。"""
    if not os.path.isdir(project_dir):
        return 0.0
    try:
        # 使用 find 命令找出 10 分鐘內是否有變動，或直接抓最後一個 mtime
        cmd = f"find {project_dir} -maxdepth 3 -not -path '*/.*' -type f -printf '%T@\\n' | sort -n | tail -1"
        res = os.popen(cmd).read().strip()
        return float(res) if res else 0.0
    except:
        return 0.0


def run_ecosystem_report() -> str:
    """屏障同步 (Barrier Sync) 機制：清空簽到處 -> 檢查各專案 -> 回報狀態。"""
    sync_dir = os.path.join(AGENT_DATA_ROOT, "runtime", "ecosystem_sync")
    os.makedirs(sync_dir, exist_ok=True)
    
    # 1. 清空舊的簽到鏈結 (The Clear)
    os.system(f"rm -rf {sync_dir}/*")
    
    report = ["# 🌐 Antigravity Agent OS: Ecosystem Report (Barrier-Sync)", ""]
    
    # 獲取所有專案
    status_paths = sorted(glob(os.path.join(CENTRAL_PROJECTS_DIR, "*", "STATUS.md")))
    expected_count = len(status_paths)
    synced_count = 0
    needs_update = []

    for status_path in status_paths:
        project_name = os.path.basename(os.path.dirname(status_path))
        
        # 讀取 STATUS.md 查看實際代碼路徑
        content = read_file(status_path)
        actual_path = extract_summary_field(content, "Actual Code Path")
        reported_date_str = extract_summary_field(content, "Last Updated")
        
        # 2. 檢測新鮮度 (Freshness Check)
        is_fresh = True
        status_mtime = os.path.getmtime(status_path)
        
        if actual_path and os.path.exists(actual_path):
            code_last_change = get_project_last_change(actual_path)
            # 如果程式碼變動晚於狀態更新 (給予 60 秒誤差)
            if code_last_change > status_mtime + 60:
                is_fresh = False
        
        if is_fresh:
            # 專案狀態已同步：建立簽到鏈結 (The Sign-in)
            link_path = os.path.join(sync_dir, f"{project_name}.md")
            os.symlink(status_path, link_path)
            synced_count += 1
        else:
            needs_update.append(project_name)

    # 3. 系統指標彙整
    uptime_p = os.popen("uptime -p").read().strip().replace("up ", "")
    mem_full = os.popen("free -h | grep Mem").read().strip()
    mem_brief = parse_memory_brief()
    
    report.extend([
        "## 🖥️ System Health & Sync Status",
        f"- **OS Uptime**: {uptime_p}",
        f"- **Memory**: {mem_full}",
        f"- **Barrier Sync**: `{synced_count}/{expected_count}` Projects Verified",
        ""
    ])
    
    if needs_update:
        report.append("### ⚠️ Needs Attention (Stale Projects)")
        report.append("以下專案代碼有變動，但 `STATUS.md` 尚未更新：")
        for p in needs_update:
            report.append(f"- `[x]` {p} (Run `/report` in this project)")
        report.append("")

    # 4. 專案矩陣彙整
    report.append("## 📂 Current Project Matrix")
    report.append("| Project | Ver. Status | Last Updated | Latest Activity |")
    report.append("| :--- | :--- | :--- | :--- |")
    
    tg_rows = []
    for status_path in status_paths:
        p_name = os.path.basename(os.path.dirname(status_path))
        p_content = read_file(status_path)
        p_status = extract_summary_field(p_content, "Last Status") or "N/A"
        p_updated = extract_summary_field(p_content, "Last Updated") or "N/A"
        p_activity = extract_latest_log(p_content) or "N/A"
        
        v_tag = "🟢 Verified" if p_name not in needs_update else "🔴 Stale"
        report.append(f"| **{p_name}** | {v_tag} | {p_updated} | {p_activity} |")
        tg_rows.append({'name': p_name, 'tag': v_tag, 'updated': p_updated})

    output = "\n".join(report)
    
    # 存檔至日誌
    history_dir = os.path.join(AGENT_DATA_ROOT, "journals", "ecosystem_reports")
    os.makedirs(history_dir, exist_ok=True)
    from datetime import datetime
    file_path = os.path.join(history_dir, f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.md")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(output)
    
    # Send formatted report to Telegram
    tg_message = format_telegram_report(
        uptime_p, mem_brief, synced_count, expected_count, needs_update, tg_rows
    )
    send_telegram_notification(tg_message)
        
    return output


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: run_workflow.py <workflow-name|/command|list>")
        return 1

    workflow_name = normalize_workflow_name(sys.argv[1])
    if workflow_name == "list":
        for name in discover_workflows():
            print(f"/{name}")
        return 0

    if workflow_name == "status":
        print(run_status())
        return 0
        
    if workflow_name == "ecosystem-report":
        print(run_ecosystem_report())
        return 0

    if workflow_name == "setup":
        setup_script = os.path.join(PROJECT_ROOT, "scripts", "setup_env.py")
        # 直接執行，因為 setup_env.py 是互動性的，
        # 在 run_workflow.py 中如果是 subprocess 可能需要特殊處理 stdin，
        # 但這裡我們假設是在 terminal 執行。
        subprocess.run(["python3", setup_script], cwd=PROJECT_ROOT)
        return "✅ /setup started. Follow instructions in the terminal."

    if workflow_name == "report":
        # 先執行原本的 report 操作 (這裡假設 report 是手動 md 導引，但我們在此加入自動交接)
        handover_script = os.path.join(PROJECT_ROOT, "scripts", "handover.py")
        subprocess.run(["python3", handover_script], cwd=PROJECT_ROOT)
        return "✅ /report complete. Context handover generated."

    print(run_generic(workflow_name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
