import os
import re
from datetime import datetime

class TaskArchitect:
    def __init__(self, project_path):
        self.project_path = project_path
        self.spec_path = os.path.join(project_path, "SPEC.md")
        self.tasks_path = os.path.join(project_path, "TASKS.md")

    def get_progress(self):
        if not os.path.exists(self.tasks_path): return 0
        with open(self.tasks_path, "r", encoding="utf-8") as f: content = f.read()
        tasks = re.findall(r'- \[([ xX])\]', content)
        if not tasks: return 0
        done = sum(1 for t in tasks if t.strip().lower() == 'x')
        return int((done / len(tasks)) * 100)
