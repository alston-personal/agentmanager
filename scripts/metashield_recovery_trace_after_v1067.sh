#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol
OUT=${1:-/tmp/metashield-recovery-trace-after-v1067.json}
python3 - "$ROOT" "$OUT" <<'PY'
import json,re,sys
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2])
res={}
# Current deployed source/manifest facts only
try:
    res['extensionVersion']=json.loads((root/'extension/manifest.json').read_text()).get('version')
except Exception:
    res['extensionVersion']=None
page=root/'web-feed/app/[wallet_address]/[platform]/page.tsx'
src=page.read_text(errors='replace') if page.exists() else ''
res['sourceContract']={
  'hasRecoveryFallbackCall':'restoreWithLocalAAndVaultB()' in src,
  'restoreReturnsBoolean':bool(re.search(r'const\s+restoreWithLocalAAndVaultB\s*=\s*async\s*\(\)\s*=>\s*\{[\s\S]{0,5000}?return\s+true;',src)),
  'hasRetryAfterRecovery':bool(re.search(r'restoreWithLocalAAndVaultB\(\)[\s\S]{0,1500}?decryptPostData\(',src)),
}
# Recent server recovery lines; redact tokens/shares/credential ids and long blobs.
lines=[]
for p in [Path('/home/ubuntu/.pm2/logs/chamber-api-out.log'),Path('/home/ubuntu/.pm2/logs/chamber-api-error.log')]:
    if not p.exists(): continue
    try: tail=p.read_text(errors='replace').splitlines()[-1200:]
    except: continue
    for line in tail:
        if re.search(r'Recovery|passkey|authenticate|RESTORE_RECOVERY|vault',line,re.I):
            s=line
            s=re.sub(r'([A-Za-z0-9_-]{48,})','<redacted>',s)
            s=re.sub(r'("?(?:shareB|credentialId|sessionToken|token)"?\s*[:=]\s*)[^,}\s]+',r'\1<redacted>',s,flags=re.I)
            lines.append({'source':p.name,'text':s[-500:]})
res['recentRecoveryLines']=lines[-120:]
# Count markers to see if latest user attempt reached server auth.
joined='\n'.join(x['text'] for x in lines[-120:])
res['markers']={
 'authOptionsSeen':bool(re.search(r'authentication options|authenticate/options|auth options',joined,re.I)),
 'authVerifySeen':bool(re.search(r'authentication verified|authenticate/verify|verification',joined,re.I)),
 'restoreABSeen':bool(re.search(r'RESTORE_RECOVERY_AB|restore.*A.*B|recovery.*restor',joined,re.I)),
 'errorSeen':bool(re.search(r'error|failed|fail|invalid|unavailable',joined,re.I)),
}
out.write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n')
print(out)
PY
