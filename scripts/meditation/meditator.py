import datetime
import os
import re
import subprocess
import json
import requests
from pathlib import Path

# --- Configuration ---
AGENT_DATA_ROOT = "/home/ubuntu/agent-data"
AGENT_REPO_ROOT = "/home/ubuntu/agentmanager"
JOURNAL_PATH = f"{AGENT_DATA_ROOT}/journals/meditation"
SESSION_SYNC_FILE = f"{AGENT_DATA_ROOT}/memory/session_sync.md"
MAINTENANCE_LOG = f"{AGENT_REPO_ROOT}/maintenance.log"
TG_BRIDGE_LOG = f"{AGENT_REPO_ROOT}/tg_bridge.log"

# Load API Key from .env
def get_gemini_api_key():
    env_file = Path(f"{AGENT_REPO_ROOT}/.env")
    if not env_file.exists():
        return None
    with open(env_file, "r") as f:
        for line in f:
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=")[1].strip()
    return None

def run_grep_count(file, pattern):
    if not os.path.exists(file):
        return 0
    try:
        # Using subprocess to call grep as it's faster for large files
        result = subprocess.run(["grep", "-c", pattern, file], capture_output=True, text=True)
        return int(result.stdout.strip()) if result.returncode == 0 else 0
    except:
        return 0

def get_last_n_lines(file, n=100):
    if not os.path.exists(file):
        return ""
    try:
        result = subprocess.run(["tail", "-n", str(n), file], capture_output=True, text=True)
        return result.stdout
    except:
        return ""

def call_gemini(api_key, system_prompt, user_prompt):
    # Using the discovery: gemini-2.5-flash is available!
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    data = {"contents": [{"parts": [{"text": f"System: {system_prompt}\n\nUser: {user_prompt}"}]}]}
    try:
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"Error calling Gemini: {e}\nResponse: {response.text if 'response' in locals() else 'No response'}"

def meditate():
    print(f"[{datetime.datetime.now()}] meditation started...")
    
    # Statistics Collection
    stats = {
        "date": datetime.datetime.now().strftime("%Y-%m-%d"),
        "total_session_events": run_grep_count(SESSION_SYNC_FILE, "## Session Event"),
        "success_count": run_grep_count(SESSION_SYNC_FILE, "✅") + run_grep_count(MAINTENANCE_LOG, "✅"),
        "failure_count": run_grep_count(SESSION_SYNC_FILE, "❌") + run_grep_count(MAINTENANCE_LOG, "Error"),
        "warning_count": run_grep_count(MAINTENANCE_LOG, "WARNING"),
    }
    
    # Get last events snippet for context
    events_context = get_last_n_lines(SESSION_SYNC_FILE, 100)
    logs_context = get_last_n_lines(MAINTENANCE_LOG, 50)
    
    # Determine top projects from session_sync
    projects = re.findall(r"Handover: `([^`]+)`", events_context)
    active_projects = sorted(list(set(projects)), key=lambda p: projects.count(p), reverse=True)[:3]
    stats["top_active_projects"] = active_projects
    
    # Gemini Self-Reflection
    api_key = get_gemini_api_key()
    if not api_key:
        stats["reflection"] = "Missing API Key for self-reflection."
        stats["upgrade_proposals"] = []
    else:
        system_prompt = (
            "You are the AgentManager Meditation Brain. Your role is self-evaluation and system-level introspection. "
            "Analyze the provided log statistics and context to find bottlenecks, report stability, and propose logical upgrades to the system architecture."
        )
        user_prompt = f"""
Current System Stats:
- Events Today: {stats['total_session_events']}
- Success Rate: {stats['success_count']} / {stats['success_count'] + stats['failure_count']}
- Warnings: {stats['warning_count']}
- Top Active Projects: {', '.join(active_projects)}

Recent Log Context:
{logs_context}

Please provide:
1. A summary of today's achievements and health.
2. At least 3 specific observations on system bottlenecks or repeated errors.
3. 2 architectural evolution proposals (e.g., refactoring suggestions, new prompt rules, or automation improvements).
Format the response in Markdown suitable for a journal entry.
        """
        stats["reflection"] = call_gemini(api_key, system_prompt, user_prompt)

    # Compile the Report
    report_md = f"""# 🧘‍♂️ AgentManager Daily Meditation - {stats['date']}

## 📊 Performance Inventory
| Metric | Value |
| :--- | :--- |
| **Total Events** | {stats['total_session_events']} |
| **Success / Fail** | ✅ {stats['success_count']} / ❌ {stats['failure_count']} |
| **Warnings** | ⚠️ {stats['warning_count']} |
| **Top Projects** | {', '.join(active_projects)} |

## 🧬 Self-Reflection & Evolution
{stats['reflection']}

---
*Meditation metadata: generated at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""

    # Ensure journal directory exists and save
    os.makedirs(JOURNAL_PATH, exist_ok=True)
    report_file = f"{JOURNAL_PATH}/{stats['date']}.md"
    with open(report_file, "w") as f:
        f.write(report_md)
    
    # Update AI Command Center STATUS.md (Self-Reporting)
    cc_status_file = f"{AGENT_DATA_ROOT}/projects/ai-command-center/STATUS.md"
    if os.path.exists(cc_status_file):
        with open(cc_status_file, "r") as f:
            content = f.read()
        
        # Insert new log entry at the top of LOG_START
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        new_entry = f"- `{timestamp}` 🧘‍♂️ **MEDITATION**: Completed automated self-reflection. (Success: {stats['success_count']} / Warnings: {stats['warning_count']})\n"
        
        if "<!-- LOG_START -->" in content:
            updated_content = content.replace("<!-- LOG_START -->", f"<!-- LOG_START -->\n{new_entry}")
            # Update metric Table (Last Updated)
            updated_content = re.sub(r"\|\s+\*\*Last Updated\*\*\s+\|\s+[^|]+\s+\|", f"| **Last Updated** | {timestamp} |", updated_content)
            
            with open(cc_status_file, "w") as f:
                f.write(updated_content)

    print(f"[{datetime.datetime.now()}] meditation complete. Journal: {report_file}")

if __name__ == "__main__":
    meditate()
