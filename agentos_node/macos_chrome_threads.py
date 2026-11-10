from __future__ import annotations

import json
import platform
import subprocess
from typing import Any

_ALLOWED_PREFIXES = (
    "https://www.threads.com/messages",
    "https://threads.com/messages",
)

def _run_osascript(source: str, timeout: int = 20) -> str:
    if platform.system() != "Darwin":
        raise RuntimeError("macOS Chrome bridge requires Darwin")
    p = subprocess.run(
        ["osascript", "-e", source],
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if p.returncode != 0:
        detail = (p.stderr or p.stdout or "osascript failed")[-1200:]
        raise RuntimeError(detail)
    return p.stdout.strip()

def inspect_threads_tabs() -> dict[str, Any]:
    source = r'''
tell application "Google Chrome"
  set rows to {}
  repeat with w in windows
    repeat with t in tabs of w
      set u to URL of t
      if u starts with "https://www.threads.com/messages" or u starts with "https://threads.com/messages" then
        set end of rows to ((title of t) & tab & u)
      end if
    end repeat
  end repeat
  return rows
end tell
'''
    raw = _run_osascript(source)
    tabs = []
    for row in [x.strip() for x in raw.split(", ") if x.strip()]:
        title, _, url = row.partition("\t")
        if url.startswith(_ALLOWED_PREFIXES):
            tabs.append({"title": title[:500], "url": url[:2000]})
    return {"threads_tabs": tabs, "count": len(tabs)}

def read_visible_threads_messages(max_chars: int = 30000) -> dict[str, Any]:
    limit = max(1000, min(int(max_chars), 30000))
    js = (
        "(()=>{const m=document.querySelector('main');"
        "const s=(m?m.innerText:document.body.innerText)||'';"
        f"return s.slice(0,{limit});}})()"
    )
    encoded_js = json.dumps(js)
    source = f'''
tell application "Google Chrome"
  repeat with w in windows
    repeat with t in tabs of w
      set u to URL of t
      if u starts with "https://www.threads.com/messages" or u starts with "https://threads.com/messages" then
        set bodyText to execute t javascript {encoded_js}
        return (u & linefeed & bodyText)
      end if
    end repeat
  end repeat
end tell
'''
    raw = _run_osascript(source)
    if not raw:
        return {"found": False, "url": None, "visible_text": ""}
    url, _, text = raw.partition("\n")
    if not url.startswith(_ALLOWED_PREFIXES):
        raise RuntimeError("Threads Messages tab not found")
    return {"found": True, "url": url[:2000], "visible_text": text[:limit]}
