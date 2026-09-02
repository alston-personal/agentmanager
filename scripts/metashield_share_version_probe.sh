#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol
OUT=${1:-/tmp/metashield-share-version-probe.json}
python3 - "$ROOT" "$OUT" <<'PY'
import json,re,sys
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2])
res={}
for rel in ['extension/background.js','web-feed/app/[wallet_address]/[platform]/page.tsx','api/recovery-vault.js']:
 p=root/rel
 s=p.read_text(errors='replace') if p.exists() else ''
 hits=[]
 for m in re.finditer(r'crypto\.shareVersionChanged|shareVersionChanged',s):
  pos=m.start(); lo=max(0,pos-1800); hi=min(len(s),pos+2200); w=s[lo:hi]
  fn='<top-level>'
  pre=s[:pos].splitlines()
  for line in reversed(pre[-120:]):
   mm=re.search(r'(?:async\s+)?function\s+([A-Za-z0-9_$]+)\s*\(',line)
   if mm: fn=mm.group(1); break
  # redact long literals / likely secrets
  w=re.sub(r'([A-Za-z0-9_-]{48,})','<redacted>',w)
  hits.append({'function':fn,'context':w})
 res[rel]={'count':len(hits),'hits':hits}
out.write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n')
print(out)
PY
