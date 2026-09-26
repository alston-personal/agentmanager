#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "mio_image_container_probe=WRONG_USER" >&2
  exit 2
fi

ENV_FILE="/home/ubuntu/.config/agentos/social-runtime.env"
CRED_FILE="/home/ubuntu/.local/state/agentos/social/credentials.json"
test -f "$ENV_FILE"
test -f "$CRED_FILE"

python3 - "$ENV_FILE" "$CRED_FILE" <<'PY'
from __future__ import annotations
import json, sys, urllib.request, urllib.error
from pathlib import Path

env_file=Path(sys.argv[1]); cred_file=Path(sys.argv[2])

def parse_env(path):
    out={}
    for raw in path.read_text(encoding='utf-8').splitlines():
        line=raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k,v=line.split('=',1)
        v=v.strip()
        if len(v)>=2 and ((v[0]==v[-1]=='"') or (v[0]==v[-1]=="'")):
            v=v[1:-1]
        out[k]=v
    return out

def safe_post(url, token, body):
    data=json.dumps(body,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    req=urllib.request.Request(url,data=data,headers={
        'Authorization':'Bearer '+token,
        'Content-Type':'application/json',
        'Accept':'application/json',
    },method='POST')
    try:
        with urllib.request.urlopen(req,timeout=20) as r:
            return r.status,json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        raw=e.read().decode('utf-8','replace')
        try: doc=json.loads(raw)
        except Exception: doc={}
        err=doc.get('error') if isinstance(doc,dict) else {}
        if not isinstance(err,dict): err={}
        etype=str(err.get('type') or 'unknown')
        code=str(err.get('code') or 'unknown')
        sub=str(err.get('error_subcode') or 'unknown')
        print(f'mio_image_container_probe_http={e.code}')
        print(f'mio_image_container_probe_error_type={etype}')
        print(f'mio_image_container_probe_error_code={code}')
        print(f'mio_image_container_probe_error_subcode={sub}')
        return e.code,doc

env=parse_env(env_file)
graph='https://graph.threads.net'
store=json.loads(cred_file.read_text(encoding='utf-8'))
rows=[]
for bid,item in (store.get('bindings') or {}).items():
    if not isinstance(item,dict): continue
    if item.get('product_id')!='galaxy' or item.get('platform')!='threads': continue
    if str(item.get('username') or '').lstrip('@').lower() not in {'sunlake.milkcat','mio.milkcat'}: continue
    if not item.get('provider_account_id'): continue
    rows.append((bid,item))
if not rows:
    raise SystemExit('mio_image_container_probe=NO_MIO_BINDING')
accounts={str(i.get('provider_account_id')) for _,i in rows}
if len(accounts)!=1:
    raise SystemExit('mio_image_container_probe=AMBIGUOUS_MIO_ACCOUNT')
account=next(iter(accounts))
legacy=[(b,i) for b,i in rows if b==f'galaxy:threads:{account}']
persona=[(b,i) for b,i in rows if b==f'galaxy:threads:persona:{account}']
bid,item=(legacy[0] if legacy else persona[0] if persona else rows[0])
token=str(item.get('access_token') or '')
if not token:
    raise SystemExit('mio_image_container_probe=NO_TOKEN')
print('mio_image_container_probe_binding=' + ('legacy' if bid==f'galaxy:threads:{account}' else 'persona'))

# Current full-size baseline JPEG from the failed seaside post.
image_url='https://raw.githubusercontent.com/alston-personal/agentmanager/8b091433f5773f2452632319852e7030613f7e4f/personas/mio/approved/assets/mio-seaside-fantasy-20260926-baseline.jpg'
status,doc=safe_post(graph+'/me/threads',token,{
    'media_type':'IMAGE',
    'image_url':image_url,
    'alt_text':'Current seaside baseline image container probe.',
    'text':'Mio seaside image container diagnostic probe — not published.',
})
if status!=200:
    raise SystemExit('mio_image_container_probe=CREATE_FAILED')
cid=str(doc.get('id') or '') if isinstance(doc,dict) else ''
if not cid.isdecimal():
    raise SystemExit('mio_image_container_probe=NO_CONTAINER_ID')
print('mio_image_container_probe=CREATE_PASS')
print('mio_image_container_probe_publish=NOT_CALLED')
PY
