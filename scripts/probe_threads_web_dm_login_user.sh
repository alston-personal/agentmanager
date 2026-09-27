#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "threads_web_dm_login_probe=WRONG_USER" >&2
  exit 2
fi

python3 - <<'PY'
import importlib.util, json, os, shutil
from pathlib import Path

checks={
  "xvfb": bool(shutil.which("Xvfb")),
  "x11vnc": bool(shutil.which("x11vnc")),
  "websockify": bool(shutil.which("websockify")),
  "novnc_proxy": bool(shutil.which("novnc_proxy")),
  "cloudflared": bool(shutil.which("cloudflared")),
  "ngrok": bool(shutil.which("ngrok")),
  "ssh": bool(shutil.which("ssh")),
  "node": bool(shutil.which("node")),
  "npm": bool(shutil.which("npm")),
  "playwright_python": importlib.util.find_spec("playwright") is not None,
}
import subprocess
try:
    checks["sudo_noninteractive"] = subprocess.run(["sudo","-n","true"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5).returncode == 0
except Exception:
    checks["sudo_noninteractive"] = False
novnc_dirs=[
  Path("/usr/share/novnc"),
  Path("/usr/share/noVNC"),
  Path("/opt/novnc"),
]
checks["novnc_assets"]=any(p.exists() for p in novnc_dirs)

root=Path("/home/ubuntu/agent-data/runtime/social/threads-web-dm")
root.mkdir(parents=True,exist_ok=True)
os.chmod(root,0o700)
out=root/"login-probe.json"
out.write_text(json.dumps({"schema":"agentos.threads-web-dm-login-probe/v1",**checks},sort_keys=True,indent=2)+"\n",encoding="utf-8")
os.chmod(out,0o600)

print("threads_web_dm_login_probe=PASS")
for k,v in checks.items():
    print("threads_web_dm_login_"+k+"="+str(bool(v)).lower())
PY
