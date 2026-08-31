#!/usr/bin/env bash
set -euo pipefail
BG=/home/ubuntu/metashield-protocol/extension/background.js
python3 - "$BG" <<'PY'
from pathlib import Path
import sys
lines=Path(sys.argv[1]).read_text().splitlines()
for i,l in enumerate(lines):
    if 'BACKUP_HISTORIC_POST' in l:
        lo=max(0,i-20); hi=min(len(lines),i+65)
        print(f'LINES {lo+1}-{hi}')
        for j in range(lo,hi): print(f'{j+1}: {lines[j]}')
PY
