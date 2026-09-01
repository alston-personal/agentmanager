#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol
PROJ=/home/ubuntu/agent-data/projects/metashield-protocol
OUT=${1:-/tmp/metashield-recovery-survival.json}
python3 - "$ROOT" "$PROJ" "$OUT" <<'PY'
import json, os, re, sys
from pathlib import Path
root=Path(sys.argv[1]); proj=Path(sys.argv[2]); out=Path(sys.argv[3])
res={}
# Extension version only
try: res['extensionVersion']=json.loads((root/'extension/manifest.json').read_text()).get('version')
except Exception: res['extensionVersion']=None
# Recovery vault metadata only, never shares/credentials themselves
vp=proj/'recovery-vault.json'
vr=[]
if vp.exists():
    try:
        d=json.loads(vp.read_text())
        records=d.get('records', d if isinstance(d,list) else [])
        if isinstance(records,dict): records=list(records.values())
        for r in records:
            if not isinstance(r,dict): continue
            vr.append({
              'accountIdSuffix':str(r.get('accountId') or '')[-8:],
              'identityAlias':r.get('identityAlias') or r.get('alias'),
              'ownerAddressSuffix':str(r.get('ownerAddress') or '')[-8:],
              'setIdSuffix':str(r.get('setId') or '')[-8:],
              'createdAt':r.get('createdAt'),
              'updatedAt':r.get('updatedAt'),
              'credentialPresent':bool(r.get('credentialId') or r.get('credential') or r.get('passkeyCredentialId')),
              'shareBPresent':bool(r.get('shareB') or r.get('vaultShare') or r.get('encryptedShareB')),
              'payloadFormat':r.get('payloadFormat') or r.get('format'),
            })
    except Exception as e: res['vaultParseError']=type(e).__name__
res['recoveryVaultExists']=vp.exists(); res['recoveryVaultRecordCount']=len(vr); res['recoveryVaultRecords']=vr
# Candidate persistence files: metadata only
candidates=[]
for base in [root,proj]:
    if not base.exists(): continue
    for p in base.rglob('*'):
        if not p.is_file(): continue
        name=p.name.lower()
        if any(k in name for k in ('backup','post','echo','receipt','recovery','vault','tx')) and p.suffix.lower() in ('.json','.jsonl','.ndjson','.db','.sqlite','.sqlite3'):
            try: size=p.stat().st_size
            except: size=None
            candidates.append({'path':str(p),'size':size})
res['candidatePersistenceFiles']=candidates[:200]
# Evidence of successful historical tx IDs from logs; only IDs/timestamps, no content
logs=[]
for p in [Path('/home/ubuntu/.pm2/logs/chamber-api-out.log'),Path('/home/ubuntu/.pm2/logs/chamber-api-error.log'),root/'memory/dev-errors.ndjson']:
    if not p.exists(): continue
    try:
        lines=p.read_text(errors='replace').splitlines()[-5000:]
    except: continue
    for line in lines:
        if re.search(r'(backup|media|irys|txid|transaction)',line,re.I):
            ids=re.findall(r'\b[A-Za-z0-9_-]{40,50}\b',line)
            if ids:
                ts=re.search(r'20\d\d-\d\d-\d\d[T ][0-9:.+-Z]+',line)
                logs.append({'source':p.name,'timestamp':ts.group(0) if ts else None,'txIds':ids[:4]})
res['historicalTxEvidence']=logs[-50:]
# Server source facts that determine whether recovery can reconstruct owner key
bg=(root/'extension/background.js').read_text(errors='replace') if (root/'extension/background.js').exists() else ''
res['recoveryContract']={
 'has2of3': 'split2of3' in bg and 'combine2of3' in bg,
 'hasLocalA': 'recoveryLocalShare' in bg,
 'hasVaultB': 'shareB' in bg and 'RESTORE_RECOVERY_VAULT' in bg,
 'hasRecoveryC': 'recoveryCodeC' in bg,
 'hasLegacyOwnerPreservation': 'storeLegacyOwnerKey' in bg,
}
out.write_text(json.dumps(res,ensure_ascii=False,indent=2)+"\n")
print(out)
PY
