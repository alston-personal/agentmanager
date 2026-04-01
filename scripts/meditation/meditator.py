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

# Load API Key from Data Layer (Secret Manager Integration)
def get_gemini_api_key():
    # Attempt to load from the central secret repository as defined in system architecture
    global_env = Path("/home/ubuntu/agent-data/secrets/global.env")
    if global_env.exists():
        with open(global_env, "r") as f:
            for line in f:
                if line.startswith("GEMINI_API_KEY="):
                    return line.split("=")[1].strip()
    
    # Fallback to current .env (but check if it's a placeholder)
    env_file = Path(f"{AGENT_REPO_ROOT}/.env")
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                if line.startswith("GEMINI_API_KEY="):
                    key = line.split("=")[1].strip()
                    if "[REDACTED" not in key:
                        return key
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
    # Try models in order of preference based on observed availability
    # Lite models often have higher free-tier quotas.
    models = ["gemini-2.0-flash", "gemini-flash-lite-latest", "gemini-3.1-flash-lite-preview"]
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        data = {"contents": [{"role": "user", "parts": [{"text": f"System Instruction: {system_prompt}\n\nTask: {user_prompt}"}]}]}
        try:
            response = requests.post(url, headers=headers, json=data)
            if response.status_code == 429:
                print(f"⚠️ {model} quota exceeded, trying next...")
                continue
            response.raise_for_status()
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            if model == models[-1]: # Last model failed
                error_msg = f"Error calling Gemini: {e}\nResponse: {response.text if 'response' in locals() else 'No response'}"
                print(error_msg)
                return f"⚠️ **SELF-REFLECTION FAILED**: {error_msg}"

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
    
    # Get last events snippet for context (Reading global session records)
    events_context = get_last_n_lines(SESSION_SYNC_FILE, 100)
    logs_context = get_last_n_lines(MAINTENANCE_LOG, 50)
    
    # Determine top projects from session_sync
    projects = re.findall(r"Handover: `([^`]+)`", events_context)
    active_projects = sorted(list(set(projects)), key=lambda p: projects.count(p), reverse=True)[:3]
    stats["top_active_projects"] = active_projects
    
    # Gemini Self-Reflection
    api_key = get_gemini_api_key()
    if not api_key:
        stats["reflection"] = "❌ **IDENTITY CRISIS**: Missing real API Key for self-reflection."
        stats["upgrade_proposals"] = []
    else:
        system_prompt = (
            "You are the AgentManager Meditation Brain. Your role is system-level introspection. "
            "Analyze the provided log statistics and context to find bottlenecks, report stability, and propose logical upgrades to the system architecture."
            "CRITICAL: Be honest about system degradation or ignored warnings."
        )
        user_prompt = f"""
Current System Stats ({stats['date']}):
- Events Recorded: {stats['total_session_events']}
- Success Rate: {stats['success_count']} / {stats['success_count'] + stats['failure_count']}
- Total Warnings: {stats['warning_count']}
- Top Active Projects: {', '.join(active_projects)}

Recent Log Context:
{logs_context}

Please provide:
1. Achievement/Stability Summary.
2. 3 Specific Observations of 'Shabby Architecture' or repeated failures.
3. 2 'AgentOS Reboot' architectural suggestions.
Format as Markdown journal.
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
    cc_status_file = f"{AGENT_DATA_ROOT}/projects/agentmanager/STATUS.md"
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
