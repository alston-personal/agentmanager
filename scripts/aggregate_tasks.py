import os
import glob
import re
import yaml # Using simple regex for speed if yaml not installed, but let's try to be robust

# ⚙️ Configuration
PROJECT_ROOT = os.getenv("AGENT_PROJECT_ROOT", os.getcwd())
ENV_FILE = os.path.join(PROJECT_ROOT, ".env")

def load_env():
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    key, val = line.strip().split("=", 1)
                    os.environ[key] = val.strip('"').strip("'")

load_env()

DATA_ROOT = os.getenv("AGENT_DATA_ROOT", os.path.expanduser("~/agent-data"))
PROJECTS_DIR = os.path.join(DATA_ROOT, "projects")
OUTPUT_FILE = os.path.join(DATA_ROOT, "GLOBAL_TODO_LIST.md")

def parse_metadata(content):
    meta = {"priority": 5, "category": "general"}
    match = re.search(r"^---\n(.*?)\n---", content, re.S)
    if match:
        meta_text = match.group(1)
        for line in meta_text.split("\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                k = k.strip().lower()
                v = v.strip().lower()
                if k == "priority":
                    try: meta["priority"] = int(v)
                    except: pass
                elif k == "category":
                    meta["category"] = v
    return meta

def is_task_qualified(content: str) -> bool:
    """Check if task conforms to TASK_SPECIFICATION_STANDARD.md (has verification command)."""
    if "驗收:" in content or "verify:" in content:
        return True
    # Match backticked executable shell commands
    if re.search(r"`[^`]*(?:pytest|python3|npm|test|curl|node|ss|chmod|git|bash)[^`]*`", content):
        return True
    return False

def aggregate_tasks():
    all_tasks = []
    status_files = glob.glob(os.path.join(PROJECTS_DIR, "*", "STATUS.md"))
    
    for status_file in status_files:
        project_name = os.path.basename(os.path.dirname(status_file))
        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except OSError as e:
            print(f"⚠️ Skipping unreadable status file: {status_file} ({e})")
            continue
            
        meta = parse_metadata(content)
        priority_label = f"P{meta['priority']}"
        cat_label = f"#{meta['category']}"

        # 尋找 Todo List 區塊 (支持多種格式，且不會被 ### 三級子標題提前截斷)
        todo_match = re.search(r"## (?:📅 )?Todo List\n(.*?)(?=\n## [^#]|\n#[^#]|\Z)", content, re.S | re.I)
        if todo_match:
            tasks = todo_match.group(1).strip().split('\n')
            for task in tasks:
                t_strip = task.strip()
                if t_strip.startswith("- [ ]") or t_strip.startswith("- [x]"):
                    is_done = "[x]" in t_strip
                    qualified = is_task_qualified(t_strip) if not is_done else True
                    labeled_task = {
                        "content": f"{t_strip} `[{project_name}]` {priority_label} {cat_label}",
                        "priority": meta["priority"],
                        "category": meta["category"],
                        "project": project_name,
                        "is_done": is_done,
                        "is_qualified": qualified,
                    }
                    all_tasks.append(labeled_task)
                    
    # Sorting: Priority DESC, then Project NAME
    all_tasks.sort(key=lambda x: (x["priority"], x["project"]), reverse=True)

    # Build new content
    lines = ["# 📋 Global Agent OS Todo Hub (Ranked)\n"]
    lines.append(f"*Last Updated: {os.popen('date').read().strip()}*\n\n")
    
    qualified_pending = [t for t in all_tasks if not t["is_done"] and t["is_qualified"]]
    unqualified_pending = [t for t in all_tasks if not t["is_done"] and not t["is_qualified"]]
    completed = [t for t in all_tasks if t["is_done"]]
    
    lines.append("## 🎯 Qualified Executable Tasks (合格可執行隊列 - 滿足五大要件)\n")
    lines.append("> 依據 `TASK_SPECIFICATION_STANDARD.md`，僅有具備明確驗收指令的條目允許執行器 (The Paw / Lobster) 接單執行。\n\n")
    if not qualified_pending:
        lines.append("- (None - 尚無合格可執行任務)\n")
    else:
        current_p = -1
        for t in qualified_pending:
            if t["priority"] != current_p:
                current_p = t["priority"]
                lines.append(f"\n### [Priority {current_p}]\n")
            lines.append(f"{t['content']}\n")

    lines.append("\n---\n")
    lines.append("## ⚠️ Blocked / Needs Breakdown (缺少驗收要件草案 - 執行器禁領)\n")
    lines.append("> 這些任務屬於抽象空話或缺少驗收命令，已遭物理門禁阻斷。架構師必須補齊【目標、邊界、依賴、驗收命令、交付物】後方可解鎖。\n\n")
    if not unqualified_pending:
        lines.append("- (None - 無不合規草案)\n")
    else:
        current_p = -1
        for t in unqualified_pending:
            if t["priority"] != current_p:
                current_p = t["priority"]
                lines.append(f"\n### [Draft Priority {current_p} - 禁領]\n")
            lines.append(f"{t['content']}\n")
    
    lines.append("\n---\n")
    lines.append("## ✅ Completed Tasks\n")
    if not completed:
        lines.append("- (None)\n")
    for t in completed:
        lines.append(f"{t['content']}\n")

    new_content = "".join(lines)

    # Check if content actually changed (ignoring Last Updated timestamp)
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                old_content = f.read()
            # Strip the timestamp line for comparison
            def strip_timestamp(text):
                return re.sub(r"\*Last Updated:.*?\*\n+", "", text)
            if strip_timestamp(old_content) == strip_timestamp(new_content):
                print(f"ℹ️ Tasks unchanged, skipping write to {OUTPUT_FILE} to avoid file lock conflict.")
                return
        except Exception:
            pass

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(new_content)

if __name__ == "__main__":
    aggregate_tasks()
    print(f"Successfully aggregated ranked tasks to {OUTPUT_FILE}")
