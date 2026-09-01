#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol
PROJ=/home/ubuntu/agent-data/projects/metashield-protocol
OUT=${1:-/tmp/metashield-recovery-live-failure.json}
python3 - "$ROOT" "$PROJ" "$OUT" <<'PY'
import json,re,sys
from pathlib import Path
root=Path(sys.argv[1]); proj=Path(sys.argv[2]); out=Path(sys.argv[3])
res={}
# Vault identifiers: suffix/length only.
vp=proj/'recovery-vault.json'
if vp.exists():
 d=json.loads(vp.read_text()); records=d.get('records',[])
 if isinstance(records,dict): records=list(records.values())
 res['vaultRecords']=[]
 for r in records:
  if not isinstance(r,dict): continue
  res['vaultRecords'].append({
   'idSuffix':str(r.get('id') or '')[-8:], 'idLength':len(str(r.get('id') or '')),
   'setIdSuffix':str(r.get('setId') or '')[-8:], 'identityAlias':r.get('identityAlias'),
   'payloadPresent':isinstance(r.get('payload'),dict) and bool(r.get('payload',{}).get('ciphertext')),
   'credentialPresent':isinstance(r.get('credential'),dict) and bool(r.get('credential',{}).get('id')),
  })
# Echo recovery source contract around recovery status and authentication.
page=(root/'web-feed/app/[wallet_address]/[platform]/page.tsx').read_text(errors='replace')
for token in ['GET_RECOVERY_VAULT_STATUS','/recovery/passkey/authenticate/options','/recovery/passkey/authenticate/verify','RESTORE_RECOVERY_AB','RESTORE_RECOVERY_VAULT']:
 pos=page.find(token)
 if pos<0: continue
 w=page[max(0,pos-3500):min(len(page),pos+6500)]
 keys=sorted(set(re.findall(r'\b(?:status|recovery|vault|result|auth|response|data)\.([A-Za-z_$][A-Za-z0-9_$]*)',w)))
 lits=sorted(set(x for x in re.findall(r'["\']([^"\']{1,160})["\']',w) if any(k in x.lower() for k in ('recovery','passkey','vault'))))
 res.setdefault('echoContracts',{})[token]={'fieldRefs':keys[:120],'recoveryLiterals':lits[:80]}
# Recent server logs: only recovery/passkey checkpoint text, redact IDs/tokens/long values.
entries=[]
for p in [Path('/home/ubuntu/.pm2/logs/chamber-api-out.log'),Path('/home/ubuntu/.pm2/logs/chamber-api-error.log')]:
 if not p.exists(): continue
 try: lines=p.read_text(errors='replace').splitlines()[-12000:]
 except: continue
 for line in lines:
  if not re.search(r'(recovery|passkey|webauthn|vault)',line,re.I): continue
  # Drop any long base64/hex/token-ish value. Preserve endpoint/status/error labels.
  s=re.sub(r'\b[A-Za-z0-9_+/=-]{24,}\b','<redacted>',line)
  s=re.sub(r'0x[a-fA-F0-9]{12,}','0x<redacted>',s)
  entries.append({'source':p.name,'text':s[:500]})
res['recentRecoveryLogLines']=entries[-80:]
# Static API response fields for auth options/verify.
server=(root/'api/server.js').read_text(errors='replace')
for route in ['/recovery/passkey/authenticate/options','/recovery/passkey/authenticate/verify']:
 pos=server.find(route); w=server[max(0,pos-500):min(len(server),pos+7000)] if pos>=0 else ''
 res.setdefault('apiContracts',{})[route]={
  'routePresent':pos>=0,
  'mentionsAccountId':'accountId' in w,
  'mentionsShareB':bool(re.search(r'\bshareB\b',w)),
  'mentionsSessionToken':bool(re.search(r'\bsessionToken\b',w)),
  'mentionsVault':bool(re.search(r'\bvault\b',w)),
 }
out.write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n')
print(out)
PY
