#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol
OUT=${1:-/tmp/metashield-native-passkey-bridge-excerpt.txt}
python3 - "$ROOT" "$OUT" <<'PY'
import sys,re
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2]); chunks=[]
for rel in ['extension/content.js','web-feed/app/[wallet_address]/[platform]/page.tsx']:
 p=root/rel; lines=p.read_text(errors='replace').splitlines()
 chunks.append(f'===== {rel} =====')
 hits=[i for i,l in enumerate(lines) if 'NATIVE_PASSKEY_' in l]
 seen=[]
 for i in hits:
  lo=max(0,i-28); hi=min(len(lines),i+45)
  if any(lo>=a and hi<=b for a,b in seen): continue
  seen.append((lo,hi)); chunks.append(f'--- lines {lo+1}-{hi} ---')
  for j in range(lo,hi):
   line=lines[j]
   # redact only obvious runtime secret literals, preserve code structure/contracts
   line=re.sub(r'(["\']?(?:token|secret|privateKey|shareB|recoveryCodeC)["\']?\s*[:=]\s*)["\'][^"\']+["\']',r'\1"<redacted>"',line,flags=re.I)
   chunks.append(f'{j+1}: {line}')
out.write_text('\n'.join(chunks)+'\n')
print(out)
PY
