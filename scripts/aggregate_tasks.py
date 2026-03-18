import os
import glob
import re

AGENT_DATA_ROOT = "/home/ubuntu/agent-data"
PROJECTS_DIR = os.path.join(AGENT_DATA_ROOT, "projects")
OUTPUT_FILE = os.path.join(AGENT_DATA_ROOT, "GLOBAL_TODO_LIST.md")

def aggregate_tasks():
    all_tasks = []
    status_files = glob.glob(os.path.join(PROJECTS_DIR, "*", "STATUS.md"))
    
    for status_file in status_files:
        project_name = os.path.basename(os.path.dirname(status_file))
        with open(status_file, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # 尋找 Todo List 區塊
        todo_match = re.search(r"## 📅 Todo List\n(.*?)(?=\n##|\Z)", content, re.S)
        if todo_match:
            tasks = todo_match.group(1).strip().split('\n')
            for task in tasks:
                if task.strip().startswith("- [ ]") or task.strip().startswith("- [x]"):
                    # 加上專案標籤以便視覺化
                    labeled_task = f"{task.strip()} `[{project_name}]`"
                    all_tasks.append(labeled_task)
                    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("# 📋 Global Agent OS Todo Hub\n")
        f.write(f"*Last Updated: {os.popen('date').read()}*\n\n")
        
        pending = [t for t in all_tasks if "[ ]" in t]
        completed = [t for t in all_tasks if "[x]" in t]
        
        f.write("## 🚀 Pending Tasks\n")
        if not pending: f.write("- (None)\n")
        for t in pending: f.write(f"{t}\n")
        
        f.write("\n## ✅ Completed Tasks\n")
        if not completed: f.write("- (None)\n")
        for t in completed: f.write(f"{t}\n")

if __name__ == "__main__":
    aggregate_tasks()
    print(f"Successfully aggregated tasks to {OUTPUT_FILE}")
