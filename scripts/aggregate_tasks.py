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

DATA_ROOT = os.getenv("AGENT_DATA_ROOT", "/home/ubuntu/agent-data")
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

        # 尋找 Todo List 區塊 (支持多種格式)
        todo_match = re.search(r"## (?:📅 )?Todo List\n(.*?)(?=\n##|\Z)", content, re.S | re.I)
        if todo_match:
            tasks = todo_match.group(1).strip().split('\n')
            for task in tasks:
                t_strip = task.strip()
                if t_strip.startswith("- [ ]") or t_strip.startswith("- [x]"):
                    # 加上專案標籤與優先級以便視覺化
                    labeled_task = {
                        "content": f"{t_strip} `[{project_name}]` {priority_label} {cat_label}",
                        "priority": meta["priority"],
                        "category": meta["category"],
                        "project": project_name,
                        "is_done": "[x]" in t_strip
                    }
                    all_tasks.append(labeled_task)
                    
    # Sorting: Priority DESC, then Project NAME
    all_tasks.sort(key=lambda x: (x["priority"], x["project"]), reverse=True)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("# 📋 Global Agent OS Todo Hub (Ranked)\n")
        f.write(f"*Last Updated: {os.popen('date').read().strip()}*\n\n")
        
        pending = [t for t in all_tasks if not t["is_done"]]
        completed = [t for t in all_tasks if t["is_done"]]
        
        f.write("## 🔥 Top Priority & Pending\n")
        if not pending: f.write("- (None)\n")
        else:
            current_p = -1
            for t in pending:
                if t["priority"] != current_p:
                    current_p = t["priority"]
                    f.write(f"\n### [Priority {current_p}]\n")
                f.write(f"{t['content']}\n")
        
        f.write("\n---\n")
        f.write("## ✅ Completed Tasks\n")
        if not completed: f.write("- (None)\n")
        for t in completed: f.write(f"{t['content']}\n")

if __name__ == "__main__":
    aggregate_tasks()
    print(f"Successfully aggregated ranked tasks to {OUTPUT_FILE}")
