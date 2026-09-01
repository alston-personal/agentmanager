#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol
OUT=${1:-/tmp/metashield-restore-ab-excerpt.txt}
python3 - "$ROOT" "$OUT" <<'PY'
import re,sys
from pathlib import Path
lines=(Path(sys.argv[1])/'web-feed/app/[wallet_address]/[platform]/page.tsx').read_text(errors='replace').splitlines()
out=Path(sys.argv[2]); parts=[]
for i in range(455-1,min(535,len(lines))):
 line=re.sub(r'([A-Za-z0-9_+/=-]{40,})','<redacted>',lines[i])
 parts.append(f'{i+1}: {line}')
out.write_text('\n'.join(parts)+'\n'); print(out)
PY
