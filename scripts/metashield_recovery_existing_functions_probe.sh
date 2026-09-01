#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol
OUT=${1:-/tmp/metashield-recovery-existing-functions.json}
python3 - "$ROOT" "$OUT" <<'PY'
import json,re,sys
from pathlib import Path
s=(Path(sys.argv[1])/'web-feed/app/[wallet_address]/[platform]/page.tsx').read_text(errors='replace')
out=Path(sys.argv[2])
# Parse const async arrow functions with balanced braces.
funcs=[]
for m in re.finditer(r'const\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*async\s*(?:<[^>]+>\s*)?\([^)]*\)\s*(?::[^=]+)?=>\s*\{',s):
 name=m.group(1); i=m.end(); d=1; j=i
 while j<len(s) and d:
  if s[j]=='{': d+=1
  elif s[j]=='}': d-=1
  j+=1
 body=s[m.start():j]
 if any(t in body for t in ('/recovery/passkey/authenticate/options','/recovery/passkey/authenticate/verify','RESTORE_RECOVERY_AB','RESTORE_RECOVERY_VAULT')):
  calls=sorted(set(re.findall(r'\b(?:await\s+)?([A-Za-z_$][A-Za-z0-9_$]*)\s*\(',body)))
  literals=sorted(set(x for x in re.findall(r'["\']([^"\']{1,180})["\']',body) if any(k in x.lower() for k in ('recovery','passkey','vault'))))
  funcs.append({'name':name,'startLine':s[:m.start()].count('\n')+1,'calls':calls[:120],'literals':literals[:100], 'usesAB':'RESTORE_RECOVERY_AB' in body,'usesBC':'RESTORE_RECOVERY_VAULT' in body,'authOptions':'/recovery/passkey/authenticate/options' in body,'authVerify':'/recovery/passkey/authenticate/verify' in body})
res={'functions':funcs}
out.write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n')
print(out)
PY
