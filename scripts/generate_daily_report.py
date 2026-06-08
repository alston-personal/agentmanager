#!/usr/bin/env python3
import os
import datetime
import subprocess

REPORT_DIR = "/home/dqa03/agentos/reports/daily_reports"
os.makedirs(REPORT_DIR, exist_ok=True)

today = datetime.datetime.now()
filename = os.path.join(REPORT_DIR, f"{today.strftime('%Y-%m-%d')}_health_report.md")

def run_cmd(cmd, cwd=None):
    try:
        result = subprocess.run(cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return result.stdout.strip()
    except Exception as e:
        return str(e)

content = f"""# 📊 Daily Health & Status Report
**Generated:** {today.strftime('%Y-%m-%d %H:%M:%S')}

## 1. AgentOS Repository Status
```text
{run_cmd("git status", cwd="/home/dqa03/agentos")}
```

## 2. Docker Containers Health
```text
{run_cmd("docker ps -a --format 'table {{.Names}}\\t{{.Status}}\\t{{.Ports}}' | head -n 15")}
```

## 3. System Disk Usage
```text
{run_cmd("df -h / /mnt/QMD")}
```

## 4. Pending TODOs in STATUS.md (Top 5)
```text
{run_cmd("grep -E '^\s*-\s*\[ \]' /home/dqa03/agentos/STATUS.md | head -n 5")}
```

---
*End of automated daily report.*
"""

with open(filename, "w") as f:
    f.write(content)

print(f"Report generated successfully at: {filename}")
