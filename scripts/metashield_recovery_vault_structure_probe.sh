#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol
PROJ=/home/ubuntu/agent-data/projects/metashield-protocol
OUT=${1:-/tmp/metashield-recovery-vault-structure.json}
python3 - "$ROOT" "$PROJ" "$OUT" <<'PY'
import json,re,sys
from pathlib import Path
root=Path(sys.argv[1]); proj=Path(sys.argv[2]); out=Path(sys.argv[3])
vp=proj/'recovery-vault.json'
res={'vaultExists':vp.exists()}

def shape(v, depth=0):
    if depth>4: return {'type':type(v).__name__}
    if isinstance(v,dict):
        return {'type':'object','keys':sorted(v.keys()),'children':{k:shape(x,depth+1) for k,x in v.items() if any(t in k.lower() for t in ('vault','payload','cipher','encrypt','share','credential','passkey','iv','salt','tag','account','set','owner','format'))}}
    if isinstance(v,list): return {'type':'array','length':len(v),'itemTypes':sorted(set(type(x).__name__ for x in v))}
    if isinstance(v,str): return {'type':'string','length':len(v)}
    if v is None: return {'type':'null'}
    return {'type':type(v).__name__}

if vp.exists():
    d=json.loads(vp.read_text())
    res['rootType']=type(d).__name__
    res['rootKeys']=sorted(d.keys()) if isinstance(d,dict) else []
    records=d.get('records',{}) if isinstance(d,dict) else {}
    recs=[]
    if isinstance(records,dict):
        for map_key,r in records.items():
            if not isinstance(r,dict): continue
            recs.append({
                'mapKeySuffix':str(map_key)[-8:],
                'mapKeyLength':len(str(map_key)),
                'keys':sorted(r.keys()),
                'shape':shape(r),
                'credentialPresent':any(k in r for k in ('credential','credentialId','passkeyCredentialId')),
                'encryptedContainerKeys':[k for k in r if any(t in k.lower() for t in ('vault','payload','cipher','encrypt','share','iv','tag'))],
            })
    elif isinstance(records,list):
        for idx,r in enumerate(records):
            if isinstance(r,dict): recs.append({'index':idx,'keys':sorted(r.keys()),'shape':shape(r)})
    res['records']=recs

# Static source contract only; do not execute auth or expose values.
rv=(root/'api/recovery-vault.js').read_text(errors='replace')
sv=(root/'api/server.js').read_text(errors='replace')

def extract_fn(src,name):
    m=re.search(rf'(?:export\s+)?(?:async\s+)?function\s+{re.escape(name)}\s*\(([^)]*)\)\s*\{{',src)
    if not m:return None
    i=m.end(); depth=1; j=i
    while j<len(src) and depth:
        if src[j]=='{': depth+=1
        elif src[j]=='}': depth-=1
        j+=1
    return src[m.start():j]

def return_keys(body):
    if not body:return []
    keys=[]
    for m in re.finditer(r'\breturn\s*\{([^}]{0,2500})\}',body,re.S):
        keys += re.findall(r'\b([A-Za-z_$][A-Za-z0-9_$]*)\s*:',m.group(1))
    return sorted(set(keys))

fa=extract_fn(rv,'finishAuthentication')
ba=extract_fn(rv,'beginAuthentication')
res['libraryContract']={
    'beginAuthenticationReturnKeys':return_keys(ba),
    'finishAuthenticationReturnKeys':return_keys(fa),
    'finishMentionsShareB':bool(fa and re.search(r'\bshareB\b',fa)),
    'finishMentionsSessionToken':bool(fa and re.search(r'\bsessionToken\b',fa)),
    'finishMentionsEncryptedPayload':bool(fa and re.search(r'(cipher|encrypt|payload|vault)',fa,re.I)),
}

route='/recovery/passkey/authenticate/verify'
pos=sv.find(route)
route_text=''
if pos>=0:
    route_text=sv[max(0,pos-1000):min(len(sv),pos+9000)]
response_keys=[]
for m in re.finditer(r'(?:res\.json|jsonResponse)\s*\(\s*\{([^}]{0,3000})\}',route_text,re.S):
    response_keys += re.findall(r'\b([A-Za-z_$][A-Za-z0-9_$]*)\s*:',m.group(1))
res['apiVerifyContract']={
    'routePresent':pos>=0,
    'responseKeys':sorted(set(response_keys)),
    'mentionsShareB':bool(re.search(r'\bshareB\b',route_text)),
    'mentionsVault':bool(re.search(r'\bvault\b',route_text)),
    'mentionsSessionToken':bool(re.search(r'\bsessionToken\b',route_text)),
    'callsFinishAuthentication':'finishAuthentication' in route_text,
}
out.write_text(json.dumps(res,ensure_ascii=False,indent=2)+'\n')
print(out)
PY
