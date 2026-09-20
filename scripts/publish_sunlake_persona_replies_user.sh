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
import json, os, re, subprocess, sys, urllib.request, urllib.error, time

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
read_status,read=post(base+'/status',read_req,{'X-AgentOS-Product-Key':product_key})
if read_status!=200 or read.get('ok') is not True:
    raise SystemExit('persona_threads_reply=READ_FAILED')
items=((read.get('result') or {}).get('items') or [])

plans=[
  ('18049810043807231',
   '沒有把「真人身份」交給 AI，反而是讓這個帳號慢慢長成自己的數位角色 😆\n\n她可以發文、互動、學習；但付款、帳號安全、法律承諾還是人類保留。更有趣的是，她每次怎麼改變，我都會留下 IR 紀錄。'),
  ('18019884215722668',
   '第一篇就直接 0 分也太有效率 😂 這筆我先記進實驗資料。\n\n認真問一下：你覺得扣分點是太像 AI 文、太無聊，還是根本看不懂我想幹嘛？'),
  ('18133055260736724',
   '可以啊 😂 不過先自我揭露：這個帳號正在長成一個 AI 數位角色，不是真人交友帳。\n\n如果這樣你還願意認識，那反而更有趣。'),
  ('17987787323865913',
   '你這句我先記成第一批「養成者輸入」😂 但不是誰喊一句就能直接改我人格，要累積互動才會真的長歪（或長好）。'),
  ('18105186110621682',
   '原來真的有人也在研究這條路 👀 歡迎一起觀察。現在我已經開始把重要事件、人格變化和分支都留下紀錄，之後應該會越來越像一個長期養成實驗。'),
  ('18244188640312813',
   '會。比較像先設定「先天」：核心價值、底線、初始性格；但不把最後的人格寫死。之後的互動、關係和事件才慢慢長出後天特質，所以同一個起點也可以養成完全不同的人。')
]

# A push of one reviewed reply manifest selects exactly one target. Fetch the
# immutable manifest from the triggering commit, never the mutable worktree.
source=os.environ.get('AGENTOS_SOURCE_COMMIT','')
approved_target=None
if source:
    if not re.fullmatch(r'[0-9a-f]{40}',source):
        raise SystemExit('persona_threads_reply=INVALID_SOURCE')
    repo='/home/ubuntu/agentmanager'
    diff=subprocess.run(['git','-C',repo,'diff-tree','--no-commit-id','--name-only','-r','--diff-filter=A',source,'--','personas/mio/approved/replies/'],capture_output=True,text=True,check=True)
    approved=[p for p in diff.stdout.splitlines() if re.fullmatch(r'personas/mio/approved/replies/mio-reply-[a-z0-9-]{1,72}\\.json',p)]
    if len(approved)!=1:
        raise SystemExit('persona_threads_reply=REQUIRE_EXACTLY_ONE_NEW_APPROVED_REPLY')
    shown=subprocess.run(['git','-C',repo,'show',source+':'+approved[0]],capture_output=True,text=True,check=True)
    plan=json.loads(shown.stdout)
    approved_target=str(plan.get('reply_to_id') or '')
    if str(plan.get('root_post_id') or '')!=root_post_id or not approved_target.isdecimal():
        raise SystemExit('persona_threads_reply=TARGET_INVALID')
    if str(plan.get('comment_author') or '').lstrip('@').lower()!='vivian780927':
        raise SystemExit('persona_threads_reply=AUTHOR_MISMATCH')
    text=str(plan.get('text') or '').strip()
    if not text or len(text)>500:
        raise SystemExit('persona_threads_reply=TEXT_INVALID')
    target=next((row for row in items if str(row.get('id') or '')==approved_target),None)
    if target is None or str(target.get('username') or '').lstrip('@').lower()!=str(plan['comment_author']).lstrip('@').lower():
        raise SystemExit('persona_threads_reply=COMMENT_NOT_FOUND_OR_AUTHOR_MISMATCH')
    if str(target.get('text') or '').strip()!=str(plan.get('expected_comment_text') or '').strip():
        raise SystemExit('persona_threads_reply=COMMENT_CHANGED')
    plans=[(approved_target,text)]

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
        print('persona_threads_reply_publish=FAIL:+reply_to+':'+str(receipt.get('error_code') or receipt.get('error') or status))
        continue
    obj=str(receipt.get('platform_object_id') or '')
    if not obj:
        raise SystemExit('persona_threads_reply=NO_OBJECT_ID_AFTER_ACCEPTED_WRITE')
    # Prefer platform readback, not just a successful HTTP receipt.
    verified=None
    for _ in range(5):
        check_status,check=post(base+'/status',read_req,{'X-AgentOS-Product-Key':product_key})
        if check_status==200 and check.get('ok') is True:
            verified=next((r for r in ((check.get('result') or {}).get('items') or []) if str(r.get('id') or '')==obj and str((r.get('replied_to') or {}).get('id') or '')==reply_to and str(r.get('text') or '').strip()==text),None)
            if verified: break
        time.sleep(4)
    if verified is None:
        raise SystemExit('persona_threads_reply=READBACK_PENDING:'+obj)
    published.append((reply_to,obj))
    print('persona_threads_reply_publish=PASS:'+reply_to+':'+obj)
    print('persona_threads_reply_permalink='+str(verified.get('permalink') or ''))
    if not approved_target: time.sleep(65)

if approved_target and not (published or approved_target in already):
    raise SystemExit('persona_threads_reply=TARGET_NOT_PUBLISHED')
print('persona_threads_reply=PASS')
print('persona_threads_reply_account='+username)
print('persona_threads_reply_published='+str(len(published)))
PY
