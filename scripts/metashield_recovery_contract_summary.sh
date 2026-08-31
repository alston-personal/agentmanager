#!/usr/bin/env bash
set -euo pipefail
ROOT=/home/ubuntu/metashield-protocol
OUT=${1:-/tmp/metashield-recovery-contract-summary.json}
python3 - "$ROOT" "$OUT" <<'PY'
import json,re,sys
from pathlib import Path
root=Path(sys.argv[1]); out=Path(sys.argv[2])
bg=(root/'extension/background.js').read_text(errors='replace')
sp=(root/'extension/sidepanel.js').read_text(errors='replace')
api=(root/'api/server.js').read_text(errors='replace')
va=(root/'api/recovery-vault.js').read_text(errors='replace')

def window(src,pos,before=1600,after=5000): return src[max(0,pos-before):min(len(src),pos+after)]
def ids(pattern,s): return sorted(set(re.findall(pattern,s)))
def action_contract(src, action):
    pos=src.find(action)
    if pos<0: return None
    w=window(src,pos)
    endpoints=ids(r'(?:CHAMBER_API_BASE|API_BASE|apiBase)?\s*\}?[/]?([/][A-Za-z0-9_?&=/${}.:-]+)',w)
    calls=ids(r'\b(?:await\s+)?([A-Za-z_$][A-Za-z0-9_$]*)\s*\(',w)
    keys=ids(r'\b(?:message|msg|request|payload|body)\.([A-Za-z_$][A-Za-z0-9_$]*)',w)
    return {'calls':[c for c in calls if c not in ('if','for','while','switch','catch')][:80], 'messageKeys':keys[:80], 'endpointTokens':[e for e in endpoints if 'recovery' in e.lower() or 'passkey' in e.lower() or 'vault' in e.lower()][:40]}

def route_contract(route):
    pos=api.find(route)
    if pos<0: return None
    w=window(api,pos,800,7000)
    body=ids(r'req\.body(?:\?\.)?\.([A-Za-z_$][A-Za-z0-9_$]*)',w)+ids(r'\{\s*([^}]{0,400})\}\s*=\s*req\.body',w)
    body_keys=[]
    for x in body:
        if ',' in x or ':' in x:
            body_keys += re.findall(r'\b([A-Za-z_$][A-Za-z0-9_$]*)\b',x)
        else: body_keys.append(x)
    query=ids(r'req\.query(?:\?\.)?\.([A-Za-z_$][A-Za-z0-9_$]*)',w)
    calls=ids(r'\b(?:await\s+)?([A-Za-z_$][A-Za-z0-9_$]*)\s*\(',w)
    json_keys=[]
    for m in re.finditer(r'(?:res\.json|jsonResponse)\s*\(\s*\{([^}]{0,1200})\}',w,re.S):
        json_keys += re.findall(r'\b([A-Za-z_$][A-Za-z0-9_$]*)\s*:',m.group(1))
    return {'bodyKeys':sorted(set(body_keys))[:100], 'queryKeys':query[:50], 'calls':[c for c in calls if c not in ('if','for','while','switch','catch')][:100], 'responseKeys':sorted(set(json_keys))[:100]}

def fn_signature(src,name):
    pats=[rf'(?:export\s+)?(?:async\s+)?function\s+{re.escape(name)}\s*\(([^)]*)\)',rf'(?:const|let|var)\s+{re.escape(name)}\s*=\s*(?:async\s*)?\(([^)]*)\)']
    for p in pats:
        m=re.search(p,src)
        if m: return re.sub(r'=.*','',m.group(1)).strip()
    return None

actions=['PREPARE_RECOVERY_VAULT','CONFIRM_RECOVERY_VAULT','FINALIZE_RECOVERY_VAULT','RESTORE_RECOVERY_VAULT','RESTORE_RECOVERY_AB','GET_RECOVERY_VAULT_STATUS']
routes=['/recovery/passkey/register/options','/recovery/passkey/register/verify','/recovery/passkey/register/cancel','/recovery/passkey/authenticate/options','/recovery/passkey/authenticate/verify','/recovery/vault/rotate']
fns=['beginRegistration','finishRegistration','cancelRegistration','beginAuthentication','finishAuthentication','rotateVaultRecord']
summary={'backgroundActions':{a:action_contract(bg,a) for a in actions},'sidepanel':{'messageApis':ids(r'\b([A-Za-z_$][A-Za-z0-9_$]*(?:Message|message)[A-Za-z0-9_$]*)\s*\(',sp)[:100]},'apiRoutes':{r:route_contract(r) for r in routes},'vaultFunctionSignatures':{f:fn_signature(va,f) for f in fns}}
out.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
print(out)
PY
