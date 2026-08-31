#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol
OUT=${1:-/tmp/metashield-recovery-summary.json}
python3 - "$ROOT" "$OUT" <<'PY'
import json,re,sys
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2])
files={n:root/'extension'/n for n in ('background.js','sidepanel.js','manifest.json')}
api=root/'api'/'server.js'; vault=root/'api'/'recovery-vault.js'
def text(p): return p.read_text(errors='replace') if p.exists() else ''
bg=text(files['background.js']); sp=text(files['sidepanel.js']); ap=text(api); va=text(vault)

def enclosing_functions(src, needle):
    lines=src.splitlines(); hits=[]
    for i,l in enumerate(lines):
        if needle.lower() not in l.lower(): continue
        fn=None
        for j in range(i, max(-1,i-120), -1):
            m=re.search(r'(?:async\s+)?function\s+([A-Za-z0-9_$]+)\s*\(|(?:const|let|var)\s+([A-Za-z0-9_$]+)\s*=\s*async\s*\(', lines[j])
            if m:
                fn=m.group(1) or m.group(2); break
        hits.append({'line':i+1,'function':fn or '<top-level>','token':needle})
    return hits

def action_strings(src):
    vals=set()
    for m in re.finditer(r'["\']([A-Z][A-Z0-9_]{4,})["\']',src):
        v=m.group(1)
        if any(k in v for k in ('RECOVER','RECOVERY','PASSKEY','WEBAUTHN','CREDENTIAL','RESTORE','PREPARE')): vals.add(v)
    return sorted(vals)

def route_strings(src):
    vals=[]
    for m in re.finditer(r'\b(?:app|router)\.(?:get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']',src):
        r=m.group(1)
        if any(k in r.lower() for k in ('recover','passkey','credential','vault','webauthn')): vals.append(r)
    return sorted(set(vals))
manifest={}
try: manifest=json.loads(text(files['manifest.json']))
except Exception: pass
summary={
 'version':manifest.get('version'),
 'background':{
   'navigator_credentials_get':enclosing_functions(bg,'navigator.credentials.get'),
   'navigator_credentials_create':enclosing_functions(bg,'navigator.credentials.create'),
   'self_navigator_credentials_get':enclosing_functions(bg,'self.navigator.credentials.get'),
   'runtime_send_message_count':bg.count('chrome.runtime.sendMessage'),
   'actions':action_strings(bg),
 },
 'sidepanel':{
   'navigator_credentials_get':enclosing_functions(sp,'navigator.credentials.get'),
   'navigator_credentials_create':enclosing_functions(sp,'navigator.credentials.create'),
   'runtime_on_message_count':sp.count('chrome.runtime.onMessage'),
   'actions':action_strings(sp),
 },
 'api':{'routes':route_strings(ap)},
 'vault':{'exports':sorted(set(re.findall(r'export\s+(?:async\s+)?function\s+([A-Za-z0-9_$]+)|module\.exports\s*=\s*\{([^}]+)\}',va)))},
}
out.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
print(out)
PY
