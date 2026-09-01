#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol
OUT=${1:-/tmp/metashield-unlock-recovery-excerpt.txt}
python3 - "$ROOT" "$OUT" <<'PY'
import re,sys
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2])
p=root/'web-feed/app/[wallet_address]/[platform]/page.tsx'
lines=p.read_text(errors='replace').splitlines()
ranges=[(1300,1435),(2050,2230)]
parts=[]
for lo,hi in ranges:
 parts.append(f'===== page.tsx {lo}-{hi} =====')
 for i in range(lo-1,min(hi,len(lines))):
  line=lines[i]
  # Static source only; redact accidental literal long tokens.
  line=re.sub(r'([A-Za-z0-9_+/=-]{40,})','<redacted>',line)
  parts.append(f'{i+1}: {line}')
out.write_text('\n'.join(parts)+'\n')
print(out)
PY
