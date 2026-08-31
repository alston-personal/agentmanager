#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol/extension
OUT=${1:-/tmp/metashield-passkey-bridge-contract.json}
python3 - "$ROOT" "$OUT" <<'PY'
import json,re,sys
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2])
s=(root/'content.js').read_text(errors='replace')
sp=(root/'sidepanel.js').read_text(errors='replace')

def extract_fn(src,name):
    m=re.search(rf'(?:async\s+)?function\s+{name}\s*\(([^)]*)\)\s*\{{',src)
    if not m:return None
    i=m.end(); depth=1; j=i
    while j<len(src) and depth:
        if src[j]=='{': depth+=1
        elif src[j]=='}': depth-=1
        j+=1
    body=src[i:j-1]
    endpoints=sorted(set(re.findall(r'["\'](/recovery/[^"\']+)["\']',body)))
    msgs=sorted(set(re.findall(r'["\']([A-Z][A-Z0-9_]{4,})["\']',body)))
    calls=sorted(set(re.findall(r'\b(?:await\s+)?([A-Za-z_$][A-Za-z0-9_$]*)\s*\(',body)))
    return {'params':[p.strip() for p in m.group(1).split(',') if p.strip()],'endpoints':endpoints,'messageTypes':[x for x in msgs if any(k in x for k in ('RECOVER','RECOVERY','PASSKEY','VAULT','RESTORE','PREPARE','CONFIRM','FINALIZE'))], 'calls':[c for c in calls if c not in ('if','for','while','switch','catch')][:80]}

def msg_strings(src):
    return sorted(set(x for x in re.findall(r'["\']([A-Z][A-Z0-9_]{4,})["\']',src) if any(k in x for k in ('RECOVER','RECOVERY','PASSKEY','VAULT','RESTORE','PREPARE','CONFIRM','FINALIZE'))))
res={'contentFunctions':{n:extract_fn(s,n) for n in ['createNativePasskey','authenticateNativePasskey','handleBackupClick']},'contentMessageTypes':msg_strings(s),'sidepanelMessageTypes':msg_strings(sp),'sidepanelFunctions':{n:extract_fn(sp,n) for n in ['openRecoveryTab','sendTabMessageWithRecovery','refreshRecoveryStatus']}}
out.write_text(json.dumps(res,ensure_ascii=False,indent=2)+"\n")
print(out)
PY
