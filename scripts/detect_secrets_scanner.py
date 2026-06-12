#!/usr/bin/env python3
import os
import sys
import subprocess
import logging
from pathlib import Path

# Setup agent_core
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from agent_core import project_store
from agent_core.memory_router import resolve_memory_route

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

def get_detect_secrets_bin():
    # Attempt to locate in .venv
    bin_path = PROJECT_ROOT / ".venv" / "bin" / "detect-secrets"
    hook_path = PROJECT_ROOT / ".venv" / "bin" / "detect-secrets-hook"
    
    if bin_path.exists() and hook_path.exists():
        return str(bin_path), str(hook_path)
    
    # Fallback to system wide
    import shutil
    ds = shutil.which("detect-secrets")
    dsh = shutil.which("detect-secrets-hook")
    return ds, dsh

DETECT_SECRETS_BIN, HOOK_BIN = get_detect_secrets_bin()

def run_scan(workspace):
    if not os.path.isdir(workspace):
        return
        
    baseline_path = os.path.join(workspace, ".secrets.baseline")
    if not os.path.exists(baseline_path):
        logging.warning(f"No baseline found in {workspace}. Generating one now...")
        subprocess.run(f"{DETECT_SECRETS_BIN} scan > .secrets.baseline", shell=True, cwd=workspace)
        
    logging.info(f"Scanning workspace: {workspace}")
    
    # We use git ls-files to scan all tracked files against the baseline
    cmd = f"git ls-files -z | xargs -0r {HOOK_BIN} --baseline .secrets.baseline"
    result = subprocess.run(cmd, shell=True, cwd=workspace, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    if result.returncode != 0:
        output = result.stdout.decode().strip()
        logging.error(f"[CRITICAL WARNING] Leaked secrets found in {workspace}!\n{output}")
        # Append to STATUS.md if applicable
        route = resolve_memory_route(Path(workspace))
        status_md = route.data_root / "projects" / Path(workspace).name / "STATUS.md"
        if status_md.exists():
            content = status_md.read_text()
            if "<!-- LOG_START -->" in content:
                from datetime import datetime
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                alert = f"- `{now_str}` 🚨 **[CRITICAL]** Leaked secrets detected by detect_secrets_scanner.py!\n"
                new_content = content.replace("<!-- LOG_START -->\n", "<!-- LOG_START -->\n" + alert)
                status_md.write_text(new_content)
    else:
        logging.info(f"✅ Clean. No un-baselined secrets found in {workspace}.")

def main():
    if not DETECT_SECRETS_BIN or not HOOK_BIN:
        logging.error("❌ detect-secrets not found! Cannot scan.")
        return

    logging.info("🛡️ Starting background secrets scan...")
    # Get all projects managed by AgentOS and their local workspaces
    for p in project_store.list_projects():
        local_path = PROJECT_ROOT.parent / p.project_id
        if local_path.exists() and local_path.is_dir():
            # Check if it's a git repo
            if (local_path / ".git").exists():
                run_scan(str(local_path))
    
    # Scan agentmanager itself
    if (PROJECT_ROOT / ".git").exists():
        run_scan(str(PROJECT_ROOT))
    
    logging.info("🏁 Scan complete.")

if __name__ == "__main__":
    main()
