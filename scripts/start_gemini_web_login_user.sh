#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -un)" != "ubuntu" ]; then
  echo "gemini_web_login=WRONG_USER" >&2
  exit 2
fi

STATE_ROOT="$HOME/.local/share/agentos/gemini-web"
mkdir -p "$STATE_ROOT"
chmod 700 "$STATE_ROOT"

python3 - <<'PY'
from __future__ import annotations

import json
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

CDP="http://127.0.0.1:9222"
TARGET="https://gemini.google.com/app"

def read_json(url: str, *, method: str = "GET", timeout: float = 5.0):
    request=Request(url, method=method)
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))

targets=read_json(CDP+"/json/list")
candidate=None
for item in targets if isinstance(targets,list) else []:
    if not isinstance(item,dict):
        continue
    host=(urlparse(str(item.get("url") or "")).hostname or "").lower()
    if host.endswith("gemini.google.com") or host.endswith("accounts.google.com"):
        candidate=item
        break

created=False
if candidate is None:
    # Chrome DevTools HTTP endpoint accepts PUT and opens exactly the allowlisted
    # Gemini surface in the persistent GUI profile. No generic URL is accepted.
    candidate=read_json(CDP+"/json/new?"+quote(TARGET,safe=":/"), method="PUT")
    created=True

url=str((candidate or {}).get("url") or "")
host=(urlparse(url).hostname or "").lower()
if not (host.endswith("gemini.google.com") or host.endswith("accounts.google.com")):
    raise RuntimeError("gemini_web_login_unexpected_target")

print("gemini_web_login=HUMAN_REQUIRED")
print("gemini_web_login_target="+("CREATED" if created else "EXISTING"))
print("gemini_web_login_host="+host)
print("gemini_web_handoff=desktop.remote_view")
print("gemini_web_novnc_url=http://127.0.0.1:6080/vnc.html")
print("gemini_web_persistent_profile=true")
PY
