#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol
BG="$ROOT/extension/background.js"
SP="$ROOT/extension/sidepanel.js"
API="$ROOT/api/server.js"
VAULT="$ROOT/api/recovery-vault.js"

echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "version=$(python3 -c 'import json;print(json.load(open("'$ROOT'/extension/manifest.json"))["version"])')"

echo '===== extension recovery actions / error propagation ====='
python3 - "$BG" <<'PY'
from pathlib import Path
import sys
lines=Path(sys.argv[1]).read_text().splitlines()
keys=('RESTORE_RECOVERY','RECOVER','restoreFromRecoveryVault','restoreFromLocalAAndVaultB','storeLegacyOwnerKey','navigator.credentials','webauthn','passkey')
seen=[]
for i,l in enumerate(lines):
    if any(k.lower() in l.lower() for k in keys):
        lo=max(0,i-8); hi=min(len(lines),i+24)
        rng=(lo,hi)
        if any(lo>=a and hi<=b for a,b in seen): continue
        seen.append(rng)
        print(f'--- background.js {lo+1}-{hi}')
        for j in range(lo,hi): print(f'{j+1}: {lines[j]}')
PY

echo '===== sidepanel recovery callers ====='
python3 - "$SP" <<'PY'
from pathlib import Path
import sys
lines=Path(sys.argv[1]).read_text().splitlines()
keys=('RESTORE_RECOVERY','PREPARE_RECOVERY','GET_RECOVERY','recovery','passkey')
seen=[]
for i,l in enumerate(lines):
    if any(k.lower() in l.lower() for k in keys):
        lo=max(0,i-8); hi=min(len(lines),i+28)
        rng=(lo,hi)
        if any(lo>=a and hi<=b for a,b in seen): continue
        seen.append(rng)
        print(f'--- sidepanel.js {lo+1}-{hi}')
        for j in range(lo,hi): print(f'{j+1}: {lines[j]}')
PY

echo '===== recovery API endpoints ====='
grep -nEi 'recovery|passkey|webauthn|vault|credential|assertion' "$API" | sed -n '1,260p' || true

echo '===== recovery-vault flow ====='
python3 - "$VAULT" <<'PY'
from pathlib import Path
import sys,re
lines=Path(sys.argv[1]).read_text().splitlines()
keys=('verify','assert','credential','vault','decrypt','recovery','passkey')
seen=[]
for i,l in enumerate(lines):
    if any(k in l.lower() for k in keys):
        lo=max(0,i-5); hi=min(len(lines),i+20)
        rng=(lo,hi)
        if any(lo>=a and hi<=b for a,b in seen): continue
        seen.append(rng)
        print(f'--- recovery-vault.js {lo+1}-{hi}')
        for j in range(lo,hi):
            line=lines[j]
            # Do not print literal secret/share payload values if present.
            line=re.sub(r'(["\']?(?:share|secret|privateKey|credential)["\']?\s*[:=]\s*)([^,;}]+)', r'\1<redacted-expression>', line, flags=re.I)
            print(f'{j+1}: {line}')
PY

echo '===== recent API recovery-related logs (redacted) ====='
for f in /home/ubuntu/.pm2/logs/chamber-api-out.log /home/ubuntu/.pm2/logs/chamber-api-error.log "$ROOT/memory/dev-errors.ndjson"; do
  test -f "$f" || continue
  echo "--- $f"
  tail -n 800 "$f" | grep -Ei 'recovery|passkey|webauthn|vault|credential|restore|legacy|decrypt' | tail -n 120 | \
    sed -E 's/(share|secret|privateKey|credential|token)(["=: ]+)[^ ,}\]]+/\1\2<redacted>/Ig' || true
done

echo '===== vault metadata only ====='
python3 - <<'PY'
import json, os
p='/home/ubuntu/agent-data/projects/metashield-protocol/recovery-vault.json'
print('vault_path_exists=', os.path.exists(p))
if os.path.exists(p):
    d=json.load(open(p))
    records=d.get('records', d if isinstance(d,list) else [])
    if isinstance(records,dict): records=list(records.values())
    print('vault_record_count=', len(records))
    for idx,r in enumerate(records):
        if not isinstance(r,dict): continue
        print('record', idx, {
          'identityAlias': r.get('identityAlias'),
          'ownerAddressSuffix': str(r.get('ownerAddress') or '')[-8:],
          'setIdSuffix': str(r.get('setId') or '')[-8:],
          'createdAt': r.get('createdAt'),
          'updatedAt': r.get('updatedAt'),
          'credentialPresent': bool(r.get('credentialId') or r.get('credential')),
          'payloadFormat': r.get('payloadFormat') or r.get('format'),
        })
PY
