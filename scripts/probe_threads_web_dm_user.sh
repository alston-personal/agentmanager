#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "threads_web_dm_probe=WRONG_USER" >&2
  exit 2
fi

python3 - <<'PY'
import importlib.util, json, os, shutil
from pathlib import Path

commands=("chromium","chromium-browser","google-chrome","google-chrome-stable","firefox")
found={name: bool(shutil.which(name)) for name in commands}
playwright=importlib.util.find_spec("playwright") is not None
selenium=importlib.util.find_spec("selenium") is not None
node=bool(shutil.which("node"))
npm=bool(shutil.which("npm"))
profile_candidates=[
    Path.home()/".config/chromium",
    Path.home()/".config/google-chrome",
    Path.home()/".mozilla/firefox",
]
profile_present=any(p.exists() and p.is_dir() for p in profile_candidates)
runtime=Path("/home/ubuntu/agent-data/runtime/social/threads-web-dm")
runtime.mkdir(parents=True,exist_ok=True)
os.chmod(runtime,0o700)
payload={
  "schema":"agentos.threads-web-dm-probe/v1",
  "browser_command_available":any(found.values()),
  "browser_commands":found,
  "playwright_python":playwright,
  "selenium_python":selenium,
  "node":node,
  "npm":npm,
  "browser_profile_present":profile_present,
}
p=runtime/"probe.json"
p.write_text(json.dumps(payload,sort_keys=True,indent=2)+"\n",encoding="utf-8")
os.chmod(p,0o600)
print("threads_web_dm_probe=PASS")
print("threads_web_dm_browser_available="+str(payload["browser_command_available"]).lower())
print("threads_web_dm_playwright_python="+str(playwright).lower())
print("threads_web_dm_selenium_python="+str(selenium).lower())
print("threads_web_dm_node="+str(node).lower())
print("threads_web_dm_npm="+str(npm).lower())
print("threads_web_dm_profile_present="+str(profile_present).lower())
PY
