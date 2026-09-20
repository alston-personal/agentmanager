#!/usr/bin/env python3
from __future__ import annotations
import json, os, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ENV_FILE=Path('/home/ubuntu/.config/agentos/social-runtime.env')
CRED_FILE=Path('/home/ubuntu/.local/state/agentos/social/credentials.json')
STATE_DIR=Path('/home/ubuntu/agent-data/runtime/social/experiments/ai-subscription')
PUBLIC_EXPORT_DIR=Path('/tmp/agentos-social-public')
PUBLIC_EXPORT=PUBLIC_EXPORT_DIR/'sunlake-milkcat-replies.json'
ROOT_POST_ID='18353956147218749'
BASE='http://127.0.0.1:8771/v1/social'

def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')

def env_map():
    out={}
    for raw in ENV_FILE.read_text(encoding='utf-8').splitlines():
        if '=' in raw and not raw.lstrip().startswith('#'):
            k,v=raw.split('=',1); out[k]=v.strip().strip('"').strip("'")
    return out

def post(url,payload,headers):
    req=urllib.request.Request(url,data=json.dumps(payload,separators=(',',':')).encode(),method='POST',headers={'content-type':'application/json',**headers})
    try:
        with urllib.request.urlopen(req,timeout=20) as r:
            return r.status,json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: body=json.loads(e.read().decode())
        except Exception: body={'error':'http_error'}
        return e.code,body

def req(operation,binding_id,object_id=None):
    p={'schema':'agentos.social-request/v1','product_id':'galaxy','platform':'threads','operation':operation,'account_binding_id':binding_id}
    if object_id: p['object_id']=object_id
    return p

def main():
    STATE_DIR.mkdir(parents=True,exist_ok=True)
    os.chmod(STATE_DIR,0o700)
    env=env_map()
    products=json.loads(env.get('AGENTOS_SOCIAL_PRODUCTS_JSON','{}') or '{}')
    key=str((products.get('galaxy') or {}).get('api_key') or '')
    if not key: raise SystemExit('galaxy_monitor=PRODUCT_KEY_UNAVAILABLE')
    store=json.loads(CRED_FILE.read_text(encoding='utf-8'))
    bindings=[(bid,item) for bid,item in (store.get('bindings') or {}).items() if isinstance(item,dict) and item.get('product_id')=='galaxy' and item.get('platform')=='threads' and str(item.get('username') or '').lstrip('@').lower()=='sunlake.milkcat' and str(item.get('auth_profile') or 'persona')=='persona']
    if len(bindings)!=1: raise SystemExit(f'galaxy_monitor=BINDING_COUNT_{len(bindings)}')
    bid,item=bindings[0]
    headers={'X-AgentOS-Product-Key':key}
    identity_status,ident=post(BASE+'/status',req('identity.read',bid),headers)
    posts_status,posts=post(BASE+'/status',req('post.read',bid),headers)
    if identity_status!=200 or ident.get('ok') is not True:
        raise RuntimeError('galaxy_monitor=IDENTITY_READ_FAILED')
    if posts_status!=200 or posts.get('ok') is not True:
        raise RuntimeError('galaxy_monitor=POST_READ_FAILED')
    identity=(ident.get('result') or {}).get('identity') or {}
    post_items=(posts.get('result') or {}).get('items') or []
    root=next((x for x in post_items if str(x.get('id') or '')==ROOT_POST_ID),{})
    reply_items=[]
    seen_reply_ids=set()
    for post_item in post_items[:50]:
        post_id=str(post_item.get('id') or '')
        # Refresh recently published posts even when Meta's has_replies flag lags.
        if not post_id or (post_item.get('has_replies') is False and post_id not in ('17994092795835001','18042529955827294')):
            continue
        reply_status,reply_receipt=post(BASE+'/status',req('replies.read',bid,post_id),headers)
        if reply_status!=200 or reply_receipt.get('ok') is not True:
            raise RuntimeError('galaxy_monitor=REPLIES_READ_FAILED:'+post_id)
        for item_reply in (reply_receipt.get('result') or {}).get('items') or []:
            rid=str(item_reply.get('id') or '')
            if not rid or rid in seen_reply_ids:
                continue
            seen_reply_ids.add(rid)
            item_reply=dict(item_reply)
            item_reply['_root_post_id']=post_id
            reply_items.append(item_reply)
    previous={}
    latest=STATE_DIR/'latest.json'
    if latest.exists():
        try: previous=json.loads(latest.read_text(encoding='utf-8'))
        except Exception: previous={}
    prev_ids=set(previous.get('reply_ids') or [])
    reply_ids=[str(x.get('id')) for x in reply_items if x.get('id')]
    new=[x for x in reply_items if str(x.get('id') or '') not in prev_ids]
    snapshot={
      'schema':'agentos.social-experiment-snapshot/v1',
      'captured_at':now(),
      'experiment':'ai-pays-its-subscription',
      'account':{'username':identity.get('username') or item.get('username'),'provider_account_id':identity.get('provider_account_id') or item.get('provider_account_id')},
      'root_post':{'id':ROOT_POST_ID,'permalink':root.get('permalink'),'text':root.get('text')},
      'reply_count':len(reply_items),
      'reply_ids':reply_ids,
      'new_replies':[{'id':x.get('id'),'root_post_id':x.get('_root_post_id'),'replied_to_id':(x.get('replied_to') or {}).get('id'),'is_reply_owned_by_me':bool(x.get('is_reply_owned_by_me')),'username':x.get('username'),'text':x.get('text'),'timestamp':x.get('timestamp'),'permalink':x.get('permalink')} for x in new],
      'needs_attention':bool(new),
    }
    tmp=latest.with_suffix('.tmp'); tmp.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); os.chmod(tmp,0o600); tmp.replace(latest)
    with (STATE_DIR/'history.jsonl').open('a',encoding='utf-8') as h:
        h.write(json.dumps(snapshot,ensure_ascii=False,separators=(',',':'))+'\n')
    os.chmod(STATE_DIR/'history.jsonl',0o600)

    # Publish only sanitized, already-public Threads interaction evidence across
    # the unix-user boundary. Never expose tokens, product keys, bindings or env.
    catalog={}
    history_path=STATE_DIR/'history.jsonl'
    if history_path.exists():
        for raw in history_path.read_text(encoding='utf-8').splitlines():
            try: row=json.loads(raw)
            except Exception: continue
            for reply in row.get('new_replies') or []:
                rid=str(reply.get('id') or '')
                if rid:
                    catalog[rid]={
                        'id':rid,
                        'root_post_id':reply.get('root_post_id'),
                        'replied_to_id':reply.get('replied_to_id'),
                        'is_reply_owned_by_me':bool(reply.get('is_reply_owned_by_me')),
                        'username':reply.get('username'),
                        'text':reply.get('text'),
                        'timestamp':reply.get('timestamp'),
                        'permalink':reply.get('permalink'),
                    }
    export={
      'schema':'agentos.social-public-reply-export/v1',
      'captured_at':snapshot['captured_at'],
      'experiment':snapshot['experiment'],
      'account_username':snapshot['account'].get('username'),
      'root_post_id':ROOT_POST_ID,
      'root_post_permalink':snapshot['root_post'].get('permalink'),
      'replies':list(catalog.values()),
    }
    PUBLIC_EXPORT_DIR.mkdir(parents=True,exist_ok=True)
    os.chmod(PUBLIC_EXPORT_DIR,0o755)
    pub_tmp=PUBLIC_EXPORT.with_suffix('.tmp')
    pub_tmp.write_text(json.dumps(export,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    os.chmod(pub_tmp,0o644)
    pub_tmp.replace(PUBLIC_EXPORT)
    os.chmod(PUBLIC_EXPORT,0o644)

    print('galaxy_monitor=PASS')
    print('galaxy_monitor_reply_count='+str(len(reply_items)))
    print('galaxy_monitor_new_replies='+str(len(new)))
    print('galaxy_monitor_needs_attention='+str(bool(new)).lower())

if __name__=='__main__':
    main()
