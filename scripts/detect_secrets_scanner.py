#!/usr/bin/env python3
import os
import subprocess
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

WORKSPACES = ["/home/dqa03/agentos", "/home/dqa03/system"]
DETECT_SECRETS_BIN = "/home/dqa03/agentos/venv/bin/detect-secrets"
HOOK_BIN = "/home/dqa03/agentos/venv/bin/detect-secrets-hook"

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
        status_md = Path(workspace) / "STATUS.md"
        if status_md.exists():
            content = status_md.read_text()
            if "<!-- LOG_START -->" in content:
                alert = f"- `{os.popen('date +\"%Y-%m-%d %H:%M:%S\"').read().strip()}` 🚨 **[CRITICAL]** Leaked secrets detected by detect_secrets_scanner.py!\n"
                new_content = content.replace("<!-- LOG_START -->\n", "<!-- LOG_START -->\n" + alert)
                status_md.write_text(new_content)
    else:
        logging.info(f"✅ Clean. No un-baselined secrets found in {workspace}.")

def main():
    logging.info("🛡️ Starting background secrets scan...")
    for ws in WORKSPACES:
        run_scan(ws)
    logging.info("🏁 Scan complete.")

if __name__ == "__main__":
    main()
