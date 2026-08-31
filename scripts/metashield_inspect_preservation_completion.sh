#!/usr/bin/env bash
set -u
ROOT=/home/ubuntu/metashield-protocol
BG="$ROOT/extension/background.js"
SIDE="$ROOT/extension/sidepanel.js"

echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "version=$(python3 -c 'import json;print(json.load(open("'"$ROOT"'/extension/manifest.json"))["version"])')"
echo "head=$(git -C "$ROOT" rev-parse HEAD)"

echo '===== backup success / receipt symbols ====='
grep -nE 'backup-receipt|backupReceipt|receipt|BACKUP|backup complete|Backup complete|success: true|recoveryExportConfirmedVersion|recoveryVaultStatus|logical_source_id|logicalSourceId|ownerKeyEnvelope|createOwnerEnvelope' "$BG" | sed -n '1,520p' || true

echo '===== sidepanel success / recovery symbols ====='
grep -nE 'backup|成功|success|receipt|recovery|Recovery|recoveryExportConfirmedVersion|confirmed|TxID|Echo' "$SIDE" | sed -n '1,520p' || true

echo '===== backup function contexts ====='
python3 - "$BG" <<'PY'
from pathlib import Path
import re,sys
p=Path(sys.argv[1]); s=p.read_text()
patterns=[
    r'async function processBackupTask',
    r'async function uploadToChamber',
    r'async function recoveryVaultStatus',
    r'function appendBackupReceipt',
    r'backup-receipts',
    r'logical_source_id',
    r'ownerKeyEnvelope',
]
lines=s.splitlines()
for pat in patterns:
    print('---',pat)
    rx=re.compile(pat,re.I)
    for i,line in enumerate(lines):
        if rx.search(line):
            lo=max(0,i-35); hi=min(len(lines),i+110)
            print(f'LINES {lo+1}-{hi}')
            for j in range(lo,hi): print(f'{j+1}: {lines[j]}')
            break
PY

echo '===== existing receipt file sample keys only ====='
python3 - <<'PY'
import json, pathlib
for p in [pathlib.Path('/home/ubuntu/metashield-protocol/memory/backup-receipts.ndjson'), pathlib.Path('/home/ubuntu/agent-data/projects/metashield-protocol/backup-receipts.ndjson')]:
    if not p.exists(): continue
    print('receipt_file=',p)
    rows=p.read_text(errors='ignore').splitlines()[-5:]
    for row in rows:
        try:
            d=json.loads(row)
            print('keys=',sorted(d.keys()))
            for k in ['version','txId','logical_source_id','logicalSourceId','network','recovery_coverage','recoverySetId','setId','keyId','ownerKeyId']:
                if k in d: print(k,'=',d[k])
        except Exception as e: print('parse_error=',type(e).__name__)
PY
