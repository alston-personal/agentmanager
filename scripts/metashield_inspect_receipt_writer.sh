#!/usr/bin/env bash
set -u
ROOT=/home/ubuntu/metashield-protocol
API="$ROOT/api/server.js"
echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo '===== API backup / receipt symbols ====='
grep -nE 'backup-receipt|backupReceipts|receipt|logicalSourceId|extensionVersion|protocolVersion|txId|router.post\("/backup|router.post\("/media' "$API" | sed -n '1,520p' || true
python3 - "$API" <<'PY'
from pathlib import Path
import re,sys
p=Path(sys.argv[1]); lines=p.read_text().splitlines()
for pat in [r'router.post\("/backup',r'backup-receipts',r'logicalSourceId',r'protocolVersion']:
 print('---',pat)
 rx=re.compile(pat,re.I)
 for i,l in enumerate(lines):
  if rx.search(l):
   lo=max(0,i-55); hi=min(len(lines),i+180)
   print(f'LINES {lo+1}-{hi}')
   for j in range(lo,hi): print(f'{j+1}: {lines[j]}')
   break
PY
