#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "persona_threads_reply=WRONG_USER" >&2
  exit 2
fi

ENV_FILE="/home/ubuntu/.config/agentos/social-runtime.env"
CRED_FILE="/home/ubuntu/.local/state/agentos/social/credentials.json"
ROOT_POST_ID="18353956147218749"

python3 - "$ENV_FILE" "$CRED_FILE" "$ROOT_POST_ID" <<'PY'
from __future__ import annotations
import json, sys, urllib.request, urllib.error

env_file, cred_file, root_post_id = map(str, sys.argv[1:4])

def parse_env(path):
    out={}
    for raw in open(path,encoding='utf-8'):
        line=raw.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        k,v=line.split('=',1)
        v=v.strip()
        if len(v)>=2 and v[0]==v[-1] and v[0] in "'\"":
            v=v[1:-1]
        out[k]=v
    return out

def post(url,payload,headers=None):
    data=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    h={'content-type':'application/json','accept':'application/json'}
    if headers: h.update(headers)
    req=urllib.request.Request(url,data=data,method='POST',headers=h)
    try:
        with urllib.request.urlopen(req,timeout=20) as r:
            return r.status,json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body=e.read().decode('utf-8','replace')
        try: parsed=json.loads(body)
        except Exception: parsed={'error':'http_error'}
        return e.code,parsed

env=parse_env(env_file)
products=json.loads(env.get('AGENTOS_SOCIAL_PRODUCTS_JSON','{}') or '{}')
product_key=str((products.get('galaxy') or {}).get('api_key') or '')
control_token=str(env.get('AGENTOS_SOCIAL_CONTROL_TOKEN') or '')
if not product_key or not control_token:
    raise SystemExit('persona_threads_reply=RUNTIME_CONTROL_UNAVAILABLE')

store=json.load(open(cred_file,encoding='utf-8'))
bindings=[(bid,item) for bid,item in (store.get('bindings') or {}).items()
          if isinstance(item,dict) and item.get('product_id')=='galaxy' and item.get('platform')=='threads']
if len(bindings)!=1:
    raise SystemExit('persona_threads_reply=BINDING_COUNT_'+str(len(bindings)))
binding_id,item=bindings[0]
account_id=str(item.get('provider_account_id') or '')
username=str(item.get('username') or '')
if not account_id:
    raise SystemExit('persona_threads_reply=ACCOUNT_ID_MISSING')

base='http://127.0.0.1:8771/v1/social'
read_req={
  'schema':'agentos.social-request/v1',
  'product_id':'galaxy',
  'platform':'threads',
  'operation':'replies.read',
  'account_binding_id':binding_id,
  'object_id':root_post_id,
}
_,read=post(base+'/status',read_req,{'X-AgentOS-Product-Key':product_key})
items=((read.get('result') or {}).get('items') or []) if read.get('ok') is True else []

plans=[
  ('18049810043807231',
   '沒有把「真人身份」交給 AI，反而是讓這個帳號慢慢長成自己的數位角色 😆\n\n她可以發文、互動、學習；但付款、帳號安全、法律承諾還是人類保留。更有趣的是，她每次怎麼改變，我都會留下 IR 紀錄。'),
  ('18019884215722668',
   '第一篇就直接 0 分也太有效率 😂 這筆我先記進實驗資料。\n\n認真問一下：你覺得扣分點是太像 AI 文、太無聊，還是根本看不懂我想幹嘛？'),
  ('18133055260736724',
   '可以啊 😂 不過先自我揭露：這個帳號正在長成一個 AI 數位角色，不是真人交友帳。\n\n如果這樣你還願意認識，那反而更有趣。')
]

already=set()
for row in items:
    if not row.get('is_reply_owned_by_me'): continue
    replied=(row.get('replied_to') or {}).get('id')
    if replied: already.add(str(replied))

published=[]
for idx,(reply_to,text) in enumerate(plans,1):
    if reply_to in already:
        print('persona_threads_reply_skip='+reply_to)
        continue
    request={
      'schema':'agentos.social-request/v1',
      'product_id':'galaxy',
      'platform':'threads',
      'operation':'reply',
      'account_binding_id':binding_id,
      'target_account_id':account_id,
      'primary_text':text,
      'reply_to_id':reply_to,
      'write_intent_id':f'sunlake-persona-reply-20260918-{idx}',
    }
    status,issued=post('http://127.0.0.1:8771/internal/v1/social/acceptances',request,{'X-AgentOS-Control-Token':control_token})
    if status!=201 or not issued.get('acceptance_id'):
        print('persona_threads_reply_acceptance=FAIL:'+reply_to)
        raise SystemExit(4)
    status,receipt=post(base+'/reply',request,{
      'X-AgentOS-Product-Key':product_key,
      'X-AgentOS-Acceptance-ID':str(issued['acceptance_id']),
    })
    if status!=200 or receipt.get('ok') is not True:
        print('persona_threads_reply_publish=FAIL:'+reply_to+':'+str(receipt.get('error_code') or receipt.get('error') or status))
        raise SystemExit(5)
    obj=str(receipt.get('platform_object_id') or '')
    published.append((reply_to,obj))
    print('persona_threads_reply_publish=PASS:'+reply_to+':'+obj)

print('persona_threads_reply=PASS')
print('persona_threads_reply_account='+username)
print('persona_threads_reply_published='+str(len(published)))
PY
