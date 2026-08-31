#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol
OUT=${1:-/tmp/metashield-native-passkey-contract.json}
python3 - "$ROOT" "$OUT" <<'PY'
import json,re,sys
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2])
files=[root/'extension/content.js',root/'web-feed/app/[wallet_address]/[platform]/page.tsx']
res={}
for p in files:
 s=p.read_text(errors='replace')
 entries=[]
 for token in ['NATIVE_PASSKEY_REGISTER','NATIVE_PASSKEY_AUTHENTICATE']:
  pos=s.find(token)
  if pos<0: continue
  w=s[max(0,pos-5000):min(len(s),pos+9000)]
  data_fields=sorted(set(re.findall(r'(?:event|evt|e)\.data(?:\?\.)?\.([A-Za-z_$][A-Za-z0-9_$]*)',w)))
  msg_fields=[]
  for m in re.finditer(r'postMessage\s*\(\s*\{([^}]{0,1800})\}',w,re.S):
   msg_fields += re.findall(r'\b([A-Za-z_$][A-Za-z0-9_$]*)\s*:',m.group(1))
  literals=sorted(set(x for x in re.findall(r'["\']([^"\']{1,120})["\']',w) if 'NATIVE_PASSKEY' in x))
  funcs=[]
  for m in re.finditer(r'(?:async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\(',w): funcs.append(m.group(1))
  entries.append({'token':token,'dataFields':data_fields,'postMessageFields':sorted(set(msg_fields)),'nativePasskeyLiterals':literals,'nearbyFunctions':funcs[-12:]})
 res[str(p.relative_to(root))]=entries
out.write_text(json.dumps(res,ensure_ascii=False,indent=2)+"\n")
print(out)
PY
