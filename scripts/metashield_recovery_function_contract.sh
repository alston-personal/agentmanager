#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol/extension
OUT=${1:-/tmp/metashield-recovery-function-contract.json}
python3 - "$ROOT" "$OUT" <<'PY'
import json,re,sys
from pathlib import Path
s=(Path(sys.argv[1])/'background.js').read_text(errors='replace'); out=Path(sys.argv[2])

def extract(name):
 m=re.search(rf'(?:async\s+)?function\s+{name}\s*\(([^)]*)\)\s*\{{',s)
 if not m:return None
 i=m.end(); d=1; j=i
 while j<len(s) and d:
  if s[j]=='{':d+=1
  elif s[j]=='}':d-=1
  j+=1
 b=s[i:j-1]
 strs=sorted(set(re.findall(r'["\']([^"\']{1,160})["\']',b)))
 return {
  'params':[p.strip() for p in m.group(1).split(',') if p.strip()],
  'endpointStrings':[x for x in strs if x.startswith('/') or 'chamber-api' in x or 'recovery' in x.lower() or 'vault' in x.lower() or 'passkey' in x.lower()],
  'calls':sorted(set(re.findall(r'\b(?:await\s+)?([A-Za-z_$][A-Za-z0-9_$]*)\s*\(',b)))[:120],
  'returnKeys':sorted(set(k for block in re.findall(r'\breturn\s*\{([^}]{0,1600})\}',b,re.S) for k in re.findall(r'\b([A-Za-z_$][A-Za-z0-9_$]*)\s*:',block)))[:120],
  'storageKeys':sorted(set(re.findall(r'["\'](user_[^"\']+|[^"\']*(?:recovery|Recovery|vault|Vault)[^"\']*)["\']',b)))[:120]
 }
names=['prepareRecoveryVault','confirmRecoveryVault','finalizeRecoveryVault','restoreFromRecoveryVault','restoreFromLocalAAndVaultB','recoveryVaultStatus']
out.write_text(json.dumps({n:extract(n) for n in names},ensure_ascii=False,indent=2)+"\n")
print(out)
PY
