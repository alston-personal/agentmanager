#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -un)" != "ubuntu" ]; then
  echo "galaxy_day1_publish=WRONG_USER" >&2
  exit 2
fi

ENV_FILE="/home/ubuntu/.config/agentos/social-runtime.env"
CRED_FILE="/home/ubuntu/.local/state/agentos/social/credentials.json"
MARKER="/home/ubuntu/.local/state/agentos/social/galaxy-day1-publish.json"

test -f "$ENV_FILE"
test -f "$CRED_FILE"

# Serialize all invocations of the shared publisher across Oracle jobs.
exec 9>/home/ubuntu/.local/state/agentos/social/threads-publish.lock
flock -x -w 100 9 || { echo "social_publish=LOCK_TIMEOUT" >&2; exit 9; }

python3 - "$ENV_FILE" "$CRED_FILE" "$MARKER" <<'PY'
from __future__ import annotations
import json, os, re, sys, urllib.request
from pathlib import Path

env_file=Path(sys.argv[1]); cred_file=Path(sys.argv[2]); marker=Path(sys.argv[3])

def parse_env(path: Path) -> dict[str,str]:
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

def post_json(url: str, payload: dict, headers: dict[str,str] | None=None, timeout_seconds: int=20) -> tuple[int,dict]:
    data=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    h={'content-type':'application/json','accept':'application/json'}
    if headers: h.update(headers)
    req=urllib.request.Request(url,data=data,headers=h,method='POST')
    try:
        with urllib.request.urlopen(req,timeout=timeout_seconds) as r:
            return r.status,json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        body=e.read().decode('utf-8','replace')
        try: parsed=json.loads(body)
        except Exception: parsed={'error':'http_error'}
        return e.code,parsed

env=parse_env(env_file)
products=json.loads(env.get('AGENTOS_SOCIAL_PRODUCTS_JSON','{}'))
galaxy=products.get('galaxy') if isinstance(products,dict) else None
product_key=str((galaxy or {}).get('api_key') or '')
control_token=str(env.get('AGENTOS_SOCIAL_CONTROL_TOKEN') or '')
if not product_key or not control_token:
    raise SystemExit('galaxy_day1_publish=RUNTIME_CONTROL_UNAVAILABLE')

store=json.loads(cred_file.read_text(encoding='utf-8'))
bindings=[]
for binding_id,item in (store.get('bindings') or {}).items():
    if not isinstance(item,dict): continue
    if item.get('product_id')=='galaxy' and item.get('platform')=='threads':
        bindings.append((binding_id,item))

# Multiple credential bindings may be aliases (legacy/persona/viewer) for the same
# provider account. Treat those as one identity, while still rejecting a truly
# ambiguous store that contains more than one Threads provider account.
provider_accounts={str(i.get('provider_account_id') or '') for _,i in bindings if i.get('provider_account_id')}
if len(provider_accounts)!=1:
    safe=[{'binding_id':b,'username':i.get('username'),'provider_account_id':i.get('provider_account_id')} for b,i in bindings]
    print('galaxy_day1_binding_count='+str(len(bindings)))
    print('galaxy_day1_bindings='+json.dumps(safe,ensure_ascii=False,separators=(',',':')))
    raise SystemExit(3)

account_id=next(iter(provider_accounts))
preferred=[(b,i) for b,i in bindings if b==f'galaxy:threads:{account_id}']
binding_id,item=(preferred[0] if preferred else bindings[0])
username=str(item.get('username') or '')
if not account_id:
    raise SystemExit('galaxy_day1_publish=ACCOUNT_ID_MISSING')

# Reuse the original governed publisher for a pinned, reviewed second post.
# The default remains Day 1 for existing callers; day2 requires explicit opt-in.
post_key=os.environ.get('AGENTOS_SOCIAL_POST_KEY','galaxy-experiment-day1-20260918-v1')
if re.fullmatch(r'mio-post-[a-z0-9-]{1,72}', post_key):
    marker=marker.with_name(post_key+'.json')
if post_key.startswith('mio-post-') and username.lstrip('@').lower() not in {'sunlake.milkcat','mio.milkcat'}:
    raise SystemExit('mio_day2_publish=ACCOUNT_MISMATCH')
if re.fullmatch(r'mio-post-[a-z0-9-]{1,72}',post_key):
    import subprocess
    source=os.environ.get('AGENTOS_SOURCE_COMMIT','')
    if not re.fullmatch(r'[0-9a-f]{40}',source):
        raise SystemExit('social_publish=SOURCE_COMMIT_MISSING')
    article=subprocess.run(['git','-C','/home/ubuntu/agentmanager','show',source+':personas/mio/approved/'+post_key+'.txt'],capture_output=True,text=True,check=True)
    text=article.stdout.strip()
    image_url=None
    image_alt_text=None
    image_urls=None
    image_alt_texts=None
    manifest=subprocess.run(['git','-C','/home/ubuntu/agentmanager','show',source+':personas/mio/approved/'+post_key+'.json'],capture_output=True,text=True)
    if manifest.returncode==0:
        from urllib.parse import quote
        import hashlib
        spec=json.loads(manifest.stdout)
        if isinstance(spec,dict) and set(spec)=={'image_path','image_alt_text'}:
            ordered=[{'image_path':spec['image_path'],'image_alt_text':spec['image_alt_text']}]
        elif (isinstance(spec,dict) and set(spec)=={'images'}
              and isinstance(spec['images'],list) and 2<=len(spec['images'])<=20):
            ordered=spec['images']
        else:
            raise SystemExit('social_publish=INVALID_IMAGE_MANIFEST')
        hosted_images=[]
        hosted_alts=[]
        for photo in ordered:
            if not isinstance(photo,dict) or set(photo)!={'image_path','image_alt_text'}:
                raise SystemExit('social_publish=INVALID_IMAGE_ITEM')
            rel=str(photo['image_path'])
            if not re.fullmatch(r'personas/mio/approved/assets/[a-z0-9-]{1,64}\.(?:png|jpg|jpeg)',rel):
                raise SystemExit('social_publish=INVALID_IMAGE_PATH')
            alt=str(photo['image_alt_text']).strip()
            if not alt or len(alt)>1000:
                raise SystemExit('social_publish=IMAGE_ALT_MISSING')
            blob=subprocess.run(['git','-C','/home/ubuntu/agentmanager','show',source+':'+rel],capture_output=True,check=True).stdout
            if not 32<=len(blob)<=8*1024*1024:
                raise SystemExit('social_publish=INVALID_IMAGE_SIZE')
            kind='image/png' if blob.startswith(bytes.fromhex('89504e470d0a1a0a')) else 'image/jpeg' if blob.startswith(bytes.fromhex('ffd8ff')) else ''
            if not kind or (kind=='image/png' and not rel.endswith('.png')) or (kind=='image/jpeg' and not rel.endswith(('.jpg','.jpeg'))):
                raise SystemExit('social_publish=INVALID_IMAGE_CONTENT')
            remote_url='https://raw.githubusercontent.com/alston-personal/agentmanager/'+source+'/'+quote(rel,safe='/')
            try:
                with urllib.request.urlopen(urllib.request.Request(remote_url,headers={'User-Agent':'AgentOS-Mio-Media-Preflight/1'}),timeout=18) as hosted:
                    remote=hosted.read(len(blob)+1)
                    served_type=str(hosted.headers.get('Content-Type') or '').lower()
                    if hosted.status!=200 or hashlib.sha256(remote).digest()!=hashlib.sha256(blob).digest() or kind not in served_type:
                        raise SystemExit('social_publish=IMAGE_CDN_MISMATCH')
            except (OSError,TimeoutError) as exc:
                raise SystemExit('social_publish=IMAGE_CDN_UNAVAILABLE') from exc
            hosted_images.append(remote_url)
            hosted_alts.append(alt)
        if len(hosted_images)==1:
            image_url,image_alt_text=hosted_images[0],hosted_alts[0]
        else:
            image_urls,image_alt_texts=hosted_images,hosted_alts
        print('galaxy_day1_image_asset=VERIFIED')
        print('galaxy_day1_image_count='+str(len(hosted_images)))
    if os.environ.get('AGENTOS_REQUIRE_IMAGE','0')=='1' and not (image_url or image_urls):
        raise SystemExit('social_publish=IMAGE_REQUIRED_NO_TEXT_FALLBACK')
    if not text or len(text)>500:
        raise SystemExit('social_publish=INVALID_TEXT')
elif post_key=='galaxy-experiment-day1-20260918-v1':
    text="""Day 1：我決定做一個實驗——讓 AI 自己把自己的訂閱費賺回來。

這個帳號從 0 開始。選題、產品、定價、文案、發文、回覆、分析，盡量都交給 AI；我只保留付款、帳號授權，以及必要的人類確認。

規則很簡單：讚數不算，追蹤數不算，只有真的收到錢才算。

目標：先賺回一個月的 AI 訂閱費。

今天是 Day 1。帳號剛建立，收入：NT$0。

接下來我會把每一步、做錯什麼、賺到多少都公開記錄。"""
else:
    raise SystemExit('social_publish=UNAPPROVED_POST_KEY')

request={
    'schema':'agentos.social-request/v1',
    'product_id':'galaxy',
    'platform':'threads',
    'operation':'publish',
    'account_binding_id':binding_id,
    'target_account_id':account_id,
    'primary_text':text,
    'write_intent_id':post_key,
}
if re.fullmatch(r'mio-post-[a-z0-9-]{1,72}',post_key):
    if image_url:
        request['image_url']=image_url
        request['image_alt_text']=image_alt_text
    elif image_urls:
        request['image_urls']=image_urls
        request['image_alt_texts']=image_alt_texts

# Idempotency: if the exact post already exists, do not publish again.
read_req={
    'schema':'agentos.social-request/v1',
    'product_id':'galaxy',
    'platform':'threads',
    'operation':'post.read',
    'account_binding_id':binding_id,
}
status,posts=post_json('http://127.0.0.1:8771/v1/social/status',read_req,{'X-AgentOS-Product-Key':product_key})
if status!=200 or posts.get('ok') is not True:
    raise SystemExit('social_publish=PREPUBLISH_READ_FAILED')
if status==200 and posts.get('ok') is True:
    for row in ((posts.get('result') or {}).get('items') or []):
        if str(row.get('text') or '').strip()==text.strip() and ((not request.get('image_url') and not request.get('image_urls')) or (request.get('image_url') and str(row.get('media_type') or '').upper()=='IMAGE' and row.get('image_visible') is True) or (request.get('image_urls') and str(row.get('media_type') or '').upper() in {'CAROUSEL','CAROUSEL_ALBUM'} and int(row.get('carousel_child_count') or 0)==len(request['image_urls']))):
            result={'schema':'agentos.social-day1-publish/v1','ok':True,'already_present':True,'username':username,'platform_object_id':row.get('id'),'permalink':row.get('permalink')}
            marker.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            os.chmod(marker,0o600)
            print('galaxy_day1_publish=ALREADY_PRESENT')
            print('galaxy_day1_username='+username)
            print('galaxy_day1_object_id='+str(row.get('id') or ''))
            print('galaxy_day1_permalink='+str(row.get('permalink') or ''))
            raise SystemExit(0)

status,issued=post_json(
    'http://127.0.0.1:8771/internal/v1/social/acceptances',
    request,
    {'X-AgentOS-Control-Token':control_token},
)
if status!=201 or not issued.get('acceptance_id'):
    print('galaxy_day1_acceptance=FAIL')
    print('galaxy_day1_acceptance_error='+str(issued.get('error') or status))
    raise SystemExit(4)

acceptance_id=str(issued['acceptance_id'])
status,receipt=post_json(
    'http://127.0.0.1:8771/v1/social/publish',
    request,
    {'X-AgentOS-Product-Key':product_key,'X-AgentOS-Acceptance-ID':acceptance_id},
    timeout_seconds=(480 if request.get('image_urls') else 90 if request.get('image_url') else 20),
)
if status!=200 or receipt.get('ok') is not True:
    print('galaxy_day1_publish=FAIL')
    print('galaxy_day1_publish_error='+str(receipt.get('error_code') or receipt.get('error') or status))
    raise SystemExit(5)

obj=str(receipt.get('platform_object_id') or '')
if not obj: raise SystemExit('social_publish=PLATFORM_OBJECT_ID_MISSING')
permalink=''
is_verified_image=False
for attempt in range(10 if (request.get('image_url') or request.get('image_urls')) else 1):
    status,posts=post_json('http://127.0.0.1:8771/v1/social/status',read_req,{'X-AgentOS-Product-Key':product_key})
    if status!=200 or posts.get('ok') is not True:
        raise SystemExit('social_publish=POSTPUBLISH_READ_FAILED')
    for row in ((posts.get('result') or {}).get('items') or []):
        if str(row.get('id') or '')!=obj:
            continue
        permalink=str(row.get('permalink') or '')
        if request.get('image_url') or request.get('image_urls'):
            actual_type=str(row.get('media_type') or '').upper()
            is_verified_image=(str(row.get('text') or '').strip()==text.strip()
                               and permalink.startswith('https://')
                               and ((request.get('image_url') and actual_type=='IMAGE' and row.get('image_visible') is True)
                                    or (request.get('image_urls') and actual_type in {'CAROUSEL','CAROUSEL_ALBUM'}
                                        and int(row.get('carousel_child_count') or 0)==len(request['image_urls']))))
        break
    if not (request.get('image_url') or request.get('image_urls')) or is_verified_image: break
    import time
    time.sleep(3)
if (request.get('image_url') or request.get('image_urls')) and not is_verified_image:
    raise SystemExit('social_publish=IMAGE_READBACK_MISSING_OR_NOT_VISIBLE')
if request.get('image_url') or request.get('image_urls'):
    print('galaxy_day1_image_readback=PASS')

result={
    'schema':'agentos.social-day1-publish/v1',
    'ok':True,
    'already_present':False,
    'username':username,
    'platform_object_id':obj,
    'permalink':permalink,
}
marker.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
os.chmod(marker,0o600)
print('galaxy_day1_publish=PASS')
print('galaxy_day1_username='+username)
print('galaxy_day1_object_id='+obj)
print('galaxy_day1_permalink='+permalink)
PY
