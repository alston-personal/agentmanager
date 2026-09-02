#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol/extension/background.js
OUT=${1:-/tmp/metashield-restore-vault-excerpt.txt}
python3 - "$ROOT" "$OUT" <<'PY'
import re,sys
from pathlib import Path
s=Path(sys.argv[1]).read_text(errors='replace').splitlines(); out=Path(sys.argv[2])
start=None
for i,l in enumerate(s):
    if re.search(r'async\s+function\s+restoreFromRecoveryVault\s*\(',l): start=i; break
if start is None: raise SystemExit('restoreFromRecoveryVault not found')
# conservative contiguous excerpt; redact obvious runtime secrets only
lines=[]
for j in range(max(0,start-5), min(len(s),start+150)):
    line=s[j]
    line=re.sub(r'(["\']?(?:privateKey|shareB|recoveryCodeC|secret)["\']?\s*[:=]\s*)["\'][^"\']+["\']',r'\1"<redacted>"',line,flags=re.I)
    lines.append(f'{j+1}: {line}')
out.write_text('\n'.join(lines)+'\n')
print(out)
PY
