#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol
API="$ROOT/api"
echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo '===== recovery-vault source storage references ====='
grep -nE 'readFile|writeFile|JSON|sqlite|db|store|vault|accountId|createdAt|updatedAt|registeredAt' "$API/recovery-vault.js" | sed -n '1,320p' || true

echo '===== candidate recovery store files ====='
find "$API" "$ROOT/memory" -maxdepth 3 -type f \( -iname '*recover*' -o -iname '*vault*' -o -iname '*passkey*' \) -printf '%p\n' 2>/dev/null | sort | sed -n '1,120p'

python3 - <<'PY'
from pathlib import Path
import json, re, os
src=Path('/home/ubuntu/metashield-protocol/api/recovery-vault.js').read_text(errors='replace')
# Extract literal paths only; no file contents here.
for pat in [r"['\"]([^'\"]*(?:recovery|vault|passkey)[^'\"]*\.json)['\"]", r"['\"]([^'\"]*\.sqlite3?)['\"]"]:
    for m in re.finditer(pat, src, re.I):
        print('literal_store_path=', m.group(1))
PY

echo '===== safe record summaries ====='
python3 - <<'PY'
from pathlib import Path
import json, os, re, hashlib
roots=[Path('/home/ubuntu/metashield-protocol/api'),Path('/home/ubuntu/metashield-protocol/memory')]
files=[]
for root in roots:
    if not root.exists(): continue
    for p in root.rglob('*'):
        if not p.is_file(): continue
        n=p.name.lower()
        if ('recovery' in n or 'vault' in n or 'passkey' in n) and p.suffix.lower() in ('.json','.ndjson'):
            files.append(p)
for p in sorted(set(files)):
    print('FILE',p,'size=',p.stat().st_size,'mtime=',int(p.stat().st_mtime))
    try:
        text=p.read_text(errors='replace')
        data=json.loads(text)
    except Exception:
        continue
    # Normalize records without ever outputting secret-bearing values.
    if isinstance(data, dict):
        if isinstance(data.get('records'), dict): recs=list(data['records'].values())
        elif isinstance(data.get('records'), list): recs=data['records']
        elif all(isinstance(v,dict) for v in data.values()): recs=list(data.values())
        else: recs=[data]
    elif isinstance(data,list): recs=data
    else: recs=[]
    print('record_count=',len(recs))
    for i,r in enumerate(recs[:50]):
        if not isinstance(r,dict): continue
        account=str(r.get('accountId') or r.get('id') or '')
        safe={
          'index':i,
          'account_suffix': account[-8:] if account else '',
          'createdAt':r.get('createdAt') or r.get('created_at'),
          'updatedAt':r.get('updatedAt') or r.get('updated_at'),
          'registeredAt':r.get('registeredAt') or r.get('registered_at'),
          'status':r.get('status'),
          'has_shareB': bool(r.get('shareB') or r.get('encryptedShareB') or r.get('share_b')),
          'has_credential': bool(r.get('credential') or r.get('credentialId') or r.get('credential_id')),
        }
        print(json.dumps(safe,ensure_ascii=False))
PY
