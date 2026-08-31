#!/usr/bin/env bash
set -euo pipefail
STORE=/home/ubuntu/agent-data/projects/metashield-protocol/recovery-vault.json
API=http://127.0.0.1:3011/chamber-api

echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if test ! -f "$STORE"; then
  echo 'recovery_store_exists=false'
  exit 0
fi
echo 'recovery_store_exists=true'
stat -c 'store_size=%s store_mtime_epoch=%Y' "$STORE"

curl -fsS --max-time 20 "$API/identity/resolve?alias=sunlake&platform=all" -o /tmp/sunlake-resolve.json
CURRENT_WALLET=$(python3 - <<'PY'
import json
p=json.load(open('/tmp/sunlake-resolve.json'))
print((p.get('currentWallet') or '').lower())
PY
)
export CURRENT_WALLET
python3 - <<'PY'
import json, os
from pathlib import Path
p=Path('/home/ubuntu/agent-data/projects/metashield-protocol/recovery-vault.json')
data=json.loads(p.read_text())
records=data.get('records') if isinstance(data,dict) else []
records=records if isinstance(records,list) else []
current=os.environ.get('CURRENT_WALLET','').lower()
print('store_version=', data.get('version') if isinstance(data,dict) else None)
print('store_updatedAt=', data.get('updatedAt') if isinstance(data,dict) else None)
print('record_count=', len(records))
print('current_wallet=', current)
match=0
for i,r in enumerate(records):
    if not isinstance(r,dict): continue
    owner=str(r.get('ownerAddress') or '').lower()
    ismatch=bool(current and owner==current)
    if ismatch: match += 1
    # Never print payload, credential ID/public key, setup token/challenges.
    safe={
      'index':i,
      'account_suffix':str(r.get('id') or '')[-8:],
      'ownerAddress':owner,
      'matches_current_wallet':ismatch,
      'setId':str(r.get('setId') or ''),
      'identityAlias':str(r.get('identityAlias') or ''),
      'createdAt':r.get('createdAt'),
      'updatedAt':r.get('updatedAt'),
      'has_registered_passkey':bool(r.get('credential')),
      'payload_version':(r.get('payload') or {}).get('version') if isinstance(r.get('payload'),dict) else None,
    }
    print(json.dumps(safe,ensure_ascii=False))
print('matching_current_wallet_records=',match)
PY
