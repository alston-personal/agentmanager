#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, urllib.error, urllib.request
from datetime import datetime, timezone
from pathlib import Path

from agentos_node.social.post_experiment import CheckpointPolicy, build_snapshot, learning_record, next_observation

ENV_FILE=Path('/home/ubuntu/.config/agentos/social-runtime.env')
CRED_FILE=Path('/home/ubuntu/.local/state/agentos/social/credentials.json')
BASE='http://127.0.0.1:8771/v1/social'

def post(url,payload,headers):
    req=urllib.request.Request(url,data=json.dumps(payload,separators=(',',':')).encode(),method='POST',headers={'content-type':'application/json',**headers})
    try:
        with urllib.request.urlopen(req,timeout=20) as r:
            return r.status,json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: body=json.loads(e.read().decode())
        except Exception: body={'error':'http_error'}
        return e.code,body

def env_map():
    out={}
    for raw in ENV_FILE.read_text(encoding='utf-8').splitlines():
        if '=' in raw and not raw.lstrip().startswith('#'):
            k,v=raw.split('=',1); out[k]=v.strip().strip('"').strip("'")
    return out

def req(operation,binding_id,object_id=None):
    p={'schema':'agentos.social-request/v1','product_id':'galaxy','platform':'threads','operation':operation,'account_binding_id':binding_id}
    if object_id:p['object_id']=object_id
    return p

def binding_for(username):
    store=json.loads(CRED_FILE.read_text(encoding='utf-8'))
    target=username.lstrip('@').lower()
    rows=[(bid,item) for bid,item in (store.get('bindings') or {}).items()
          if isinstance(item,dict) and item.get('product_id')=='galaxy' and item.get('platform')=='threads'
          and str(item.get('username') or '').lstrip('@').lower()==target]
    if not rows: raise SystemExit('social_experiment=BINDING_UNAVAILABLE')
    ids={str(x[1].get('provider_account_id') or '') for x in rows}
    if len(ids)!=1 or not next(iter(ids)): raise SystemExit('social_experiment=ACCOUNT_BINDING_AMBIGUOUS')
    return rows[-1]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--account',required=True)
    ap.add_argument('--post-id',required=True)
    ap.add_argument('--experiment-id',required=True)
    ap.add_argument('--elapsed-minutes',type=int,required=True)
    ap.add_argument('--hypothesis',default='')
    ap.add_argument('--changed-variable',action='append',default=[])
    args=ap.parse_args()

    env=env_map(); products=json.loads(env.get('AGENTOS_SOCIAL_PRODUCTS_JSON','{}') or '{}')
    key=str((products.get('galaxy') or {}).get('api_key') or '')
    if not key: raise SystemExit('social_experiment=PRODUCT_KEY_UNAVAILABLE')
    bid,binding=binding_for(args.account); headers={'X-AgentOS-Product-Key':key}

    s,posts=post(BASE+'/status',req('post.read',bid),headers)
    if s!=200 or posts.get('ok') is not True: raise SystemExit('social_experiment=POST_READ_FAILED')
    post_item=next((x for x in ((posts.get('result') or {}).get('items') or []) if str(x.get('id') or '')==args.post_id),None)
    if not isinstance(post_item,dict): raise SystemExit('social_experiment=POST_NOT_FOUND')

    s,replies=post(BASE+'/status',req('replies.read',bid,args.post_id),headers)
    if s!=200 or replies.get('ok') is not True: raise SystemExit('social_experiment=REPLIES_READ_FAILED')
    reply_items=list((replies.get('result') or {}).get('items') or [])

    state_dir=Path('/home/ubuntu/agent-data/runtime/social/post-experiments')/args.account.lstrip('@').lower()/args.experiment_id
    state_dir.mkdir(parents=True,exist_ok=True); os.chmod(state_dir,0o700)
    latest=state_dir/'latest.json'; previous={}
    if latest.exists():
        try: previous=json.loads(latest.read_text(encoding='utf-8'))
        except Exception: previous={}
    snapshot=build_snapshot(experiment_id=args.experiment_id,account_username=args.account.lstrip('@'),post=post_item,replies=reply_items,previous_reply_ids=set(previous.get('reply_ids') or []))
    latest.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); os.chmod(latest,0o600)
    with (state_dir/'snapshots.jsonl').open('a',encoding='utf-8') as fh: fh.write(json.dumps(snapshot,ensure_ascii=False,separators=(',',':'))+'\n')
    record=learning_record(snapshot,elapsed_minutes=args.elapsed_minutes,hypothesis=args.hypothesis,changed_variables=args.changed_variable)
    with (state_dir/'learning.jsonl').open('a',encoding='utf-8') as fh: fh.write(json.dumps(record,ensure_ascii=False,separators=(',',':'))+'\n')
    nxt=next_observation(CheckpointPolicy(),elapsed_minutes=args.elapsed_minutes,snapshot=snapshot)
    (state_dir/'next.json').write_text(json.dumps(nxt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('social_experiment=PASS')
    print('social_experiment_account='+args.account.lstrip('@'))
    print('social_experiment_post_id='+args.post_id)
    print('social_experiment_new_replies='+str(len(snapshot['new_replies'])))
    print('social_experiment_needs_attention='+str(snapshot['needs_attention']).lower())
    print('social_experiment_next_elapsed_minutes='+('none' if nxt['next_elapsed_minutes'] is None else str(nxt['next_elapsed_minutes'])))

if __name__=='__main__':
    main()
