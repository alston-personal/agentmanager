#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol
OUT=${1:-/tmp/metashield-unlock-recovery-flow.json}
python3 - "$ROOT" "$OUT" <<'PY'
import json,re,sys
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2])
p=root/'web-feed/app/[wallet_address]/[platform]/page.tsx'
s=p.read_text(errors='replace')

def extract(name):
 m=re.search(rf'(?:const\s+{re.escape(name)}\s*=\s*async\s*\([^)]*\)\s*=>\s*\{{|(?:async\s+)?function\s+{re.escape(name)}\s*\([^)]*\)\s*\{{)',s)
 if not m:return None
 i=m.end(); d=1; j=i
 while j<len(s) and d:
  if s[j]=='{': d+=1
  elif s[j]=='}': d-=1
  j+=1
 b=s[m.start():j]
 calls=sorted(set(re.findall(r'\b(?:await\s+)?([A-Za-z_$][A-Za-z0-9_$]*)\s*\(',b)))
 literals=sorted(set(x for x in re.findall(r'["\']([^"\']{1,140})["\']',b) if any(k in x.lower() for k in ('decrypt','recover','passkey','vault','unlock'))))
 return {'calls':calls[:120],'recoveryLiterals':literals[:100],'mentionsRecovery':bool(re.search(r'(RECOVERY|recovery|Passkey|passkey|vault)',b)),'mentionsDecrypt':bool(re.search(r'(DECRYPT|decrypt)',b))}

names=[]
for m in re.finditer(r'const\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*async\s*\(',s):
 n=m.group(1)
 pos=m.start(); w=s[pos:pos+10000]
 if re.search(r'(DECRYPT_OWNER_DATA|decryptedContent|decrypt|unlock|解密)',w,re.I): names.append(n)
for n in ['handleDecryptPost','handleDecryptAll','decryptPost','decryptAll','handleUnlock','requestExtensionRecovery','authenticatePasskey']:
 if n in s: names.append(n)
res={'candidateFunctions':{n:extract(n) for n in sorted(set(names)) if extract(n)}}
# Event/UI references to decrypt handlers
refs=[]
for i,line in enumerate(s.splitlines(),1):
 if re.search(r'(handleDecrypt|decryptAll|unlock|解密)',line,re.I):
  safe=re.sub(r'([A-Za-z0-9_+/=-]{40,})','<redacted>',line.strip())
  refs.append({'line':i,'text':safe[:300]})
res['uiReferences']=refs[:120]
out.write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n')
print(out)
PY
