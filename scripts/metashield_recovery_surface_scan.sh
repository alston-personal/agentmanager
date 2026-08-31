#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol/extension
OUT=${1:-/tmp/metashield-recovery-surface-scan.json}
python3 - "$ROOT" "$OUT" <<'PY'
import json,re,sys
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2])
rows=[]
for p in sorted(root.rglob('*')):
    if not p.is_file() or p.suffix.lower() not in ('.js','.html','.json','.css'): continue
    try:s=p.read_text(errors='replace')
    except:continue
    low=s.lower()
    if not any(k in low for k in ('recovery','passkey','webauthn')): continue
    funcs=sorted(set(re.findall(r'(?:async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(',s)))
    interesting=[f for f in funcs if any(k in f.lower() for k in ('recover','passkey','vault','backup','restore','credential'))]
    actions=sorted(set(v for v in re.findall(r'["\']([A-Z][A-Z0-9_]{4,})["\']',s) if any(k in v for k in ('RECOVER','RECOVERY','PASSKEY','WEBAUTHN','VAULT','RESTORE'))))
    rows.append({'path':str(p.relative_to(root)),'recoveryCount':low.count('recovery'),'passkeyCount':low.count('passkey'),'webauthnCount':low.count('webauthn'),'functions':interesting[:100],'actions':actions[:100]})
out.write_text(json.dumps(rows,ensure_ascii=False,indent=2)+"\n")
print(out)
PY
