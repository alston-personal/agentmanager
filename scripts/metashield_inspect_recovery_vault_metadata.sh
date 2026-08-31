#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol
API="$ROOT/api"
BASE=http://127.0.0.1:3011/chamber-api

echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "head=$(git -C "$ROOT" rev-parse HEAD)"

echo '===== recovery route source locations ====='
grep -nE 'recovery/vault|recoveryVault|vault.*recovery|recovery.*vault' "$API/server.js" | sed -n '1,160p' || true

echo '===== recovery route source context ====='
python3 - <<'PY'
from pathlib import Path
p=Path('/home/ubuntu/metashield-protocol/api/server.js')
lines=p.read_text(errors='replace').splitlines()
hits=[i for i,l in enumerate(lines) if 'recovery/vault' in l or ('recovery' in l.lower() and 'vault' in l.lower())]
seen=set()
for i in hits:
    a=max(0,i-18); b=min(len(lines),i+45)
    key=(a,b)
    if key in seen: continue
    seen.add(key)
    print(f'--- lines {a+1}-{b}')
    for n in range(a,b):
        # redact obvious secret-bearing literals/values if any are embedded in source comments/examples
        line=lines[n]
        print(f'{n+1}: {line}')
PY

echo '===== resolve sunlake identity (safe fields only) ====='
curl -fsS --max-time 20 "$BASE/identity/resolve?alias=sunlake&platform=all" -o /tmp/sunlake-resolve.json
python3 - <<'PY'
import json
p=json.load(open('/tmp/sunlake-resolve.json'))
for k in ('success','alias','contentKey','currentWallet','identityKey','displayName','accountId','ownerUserId'):
    if k in p: print(f'{k}={p.get(k)}')
PY

echo '===== candidate account identifiers from public identity response ====='
python3 - <<'PY'
import json
p=json.load(open('/tmp/sunlake-resolve.json'))
vals=[]
for k in ('accountId','ownerUserId','identityKey','contentKey','currentWallet','alias'):
    v=p.get(k)
    if isinstance(v,str) and v.strip(): vals.append((k,v.strip()))
seen=set()
for k,v in vals:
    if v in seen: continue
    seen.add(v)
    print(k+'\t'+v)
PY
