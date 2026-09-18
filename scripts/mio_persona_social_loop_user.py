#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, time, urllib.error, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from agentos_node.antigravity_relay import AntigravityRelayClient

ENV_FILE=Path('/home/ubuntu/.config/agentos/social-runtime.env')
CRED_FILE=Path('/home/ubuntu/.local/state/agentos/social/credentials.json')
STATE_DIR=Path('/home/ubuntu/agent-data/runtime/social/persona/sunlake-milkcat')
LATEST=Path('/home/ubuntu/agent-data/runtime/social/experiments/ai-subscription/latest.json')
PERSONA_ROOT=Path('/home/ubuntu/agent-data/personas/sunlake-milkcat')
RELAY_ROOT=Path('/home/ubuntu/agent-data/runtime/antigravity-relay')
BASE='http://127.0.0.1:8771/v1/social'
LOCAL_TZ=ZoneInfo('Asia/Taipei')

def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0)

def iso(dt):
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')

def env_map():
    out={}
    for raw in ENV_FILE.read_text(encoding='utf-8').splitlines():
        if '=' in raw and not raw.lstrip().startswith('#'):
            k,v=raw.split('=',1); out[k]=v.strip().strip('"').strip("'")
    return out

def post(url,payload,headers=None):
    req=urllib.request.Request(url,data=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode(),method='POST',headers={'content-type':'application/json',**(headers or {})})
    try:
        with urllib.request.urlopen(req,timeout=25) as r:
            return r.status,json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try: body=json.loads(e.read().decode())
        except Exception: body={'error':'http_error'}
        return e.code,body

def req(operation,binding_id,object_id=None,**extra):
    p={'schema':'agentos.social-request/v1','product_id':'galaxy','platform':'threads','operation':operation,'account_binding_id':binding_id}
    if object_id: p['object_id']=object_id
    p.update({k:v for k,v in extra.items() if v is not None})
    return p

def load_json(path,default):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except Exception:return default

def save_json(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True); os.chmod(path.parent,0o700)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    os.chmod(tmp,0o600); tmp.replace(path); os.chmod(path,0o600)

def extract_json(text):
    text=(text or '').strip()
    fence=chr(96)*3
    if text.startswith(fence):
        text=text[len(fence):].lstrip()
        if text.startswith('json'): text=text[4:].lstrip()
    if text.endswith(fence): text=text[:-len(fence)].rstrip()
    start=text.find('{'); end=text.rfind('}')
    if start<0 or end<start: raise ValueError('decision_json_missing')
    return json.loads(text[start:end+1])

def persona_context():
    files={}
    for name in ('character_core.json','persona_state.json','reply_policy.json'):
        p=PERSONA_ROOT/name
        if p.is_file(): files[name]=load_json(p,{})
    events=[]
    ep=PERSONA_ROOT/'events/events.jsonl'
    if ep.is_file():
        for raw in ep.read_text(encoding='utf-8').splitlines()[-30:]:
            try: events.append(json.loads(raw))
            except Exception: pass
    return {'files':files,'recent_events':events[-12:]}

def decide_batch(items,account_username):
    local=datetime.now(LOCAL_TZ)
    context=persona_context()
    prompt=f"""You are making PRIVATE scheduling decisions for the public AI persona 澪 / Mio (@{account_username}).
Return JSON only, no markdown.

For each NEW external Threads reply, decide independently whether Mio would naturally reply.
Use her persona state, memory boundary, current local time, temporal behavior, rest/productivity profile and public secrecy rules.

Critical rules:
- Do NOT mention internal implementation terms, IR, branching, marketplace, royalty, research roadmap, hidden product mechanics, AgentOS internals, credentials, or private owner plans.
- Do not fabricate autobiographical memories. Model background knowledge is not Mio's personal memory.
- She does not need to answer every comment. Silence is valid.
- Never instant by default. Choose delay_minutes from 8 to 720 if replying.
- If currently sleeping/resting or low-energy, prefer a longer delay unless the relationship/topic strongly warrants otherwise.
- Keep public replies short/natural, in Traditional Chinese unless the commenter clearly uses another language.
- Never make payment, contract, legal, identity-security, or sensitive commitments.
- Avoid repetitive self-explanations that she is AI unless directly relevant.
- The reply should sound like a person with her current voice, not customer support.

Current local time: {local.isoformat()}
Persona context:
{json.dumps(context,ensure_ascii=False)}

New replies:
{json.dumps(items,ensure_ascii=False)}

Required schema:
{{
  "decisions":[
    {{
      "reply_id":"...",
      "should_reply":true,
      "delay_minutes":25,
      "text":"...",
      "reason_category":"relationship|question|conversation|low_value|rest|boundary|other"
    }}
  ]
}}
If should_reply=false, text must be null and delay_minutes must be null.
"""
    client=AntigravityRelayClient(RELAY_ROOT)
    cap=client.submit(
        project_id='sunlake-milkcat-persona-social',
        canonical_ir={'goal':'Let Mio autonomously decide whether, when, and how to reply to new public Threads interactions.','constraints':['public-safe output only','respect persona memory boundary','no instant-by-default','no hidden product disclosure']},
        instruction=prompt,workspace='/home/ubuntu/agentmanager')
    for _ in range(75):
        receipt=client.receipt(cap['capsule_id'])
        if receipt:
            if not receipt.get('ok'): raise RuntimeError('persona_decision_executor_failed')
            return extract_json(receipt.get('stdout') or '')
        time.sleep(2)
    raise TimeoutError('persona_decision_timeout')

def decide_outbound(candidates,account_username):
    local=datetime.now(LOCAL_TZ)
    context=persona_context()
    prompt=f"""You are deciding whether 澪 / Mio (@{account_username}), a transparently AI-operated public persona, should join ONE public Threads conversation started by someone else.

Return JSON only, no markdown.

Choose at most one candidate. It is completely valid to choose none.
Only reply when Mio has a natural, specific reason to add something useful, curious, playful, or relational.
Do NOT do growth hacking, generic compliments, engagement bait, repetitive self-promotion, or mass outreach.
Never join political persuasion, elections, tragedies, personal crises, medical/legal/financial advice, sexual content, harassment, or content involving minors.
Do not disclose internal implementation, hidden product plans, IR, branching, marketplace, research roadmap, AgentOS internals, credentials, or owner-private plans.
Do not pretend to have memories or experiences she does not have.
Keep the reply short and natural. Do not explain she is AI unless directly relevant.
Her current local time and temporal state matter; silence is valid.

Current local time: {local.isoformat()}
Persona context:
{json.dumps(context,ensure_ascii=False)}

Candidate public posts:
{json.dumps(candidates,ensure_ascii=False)}

Required schema:
{{
  "candidate_id": "..." | null,
  "should_reply": true | false,
  "delay_minutes": 15 | null,
  "text": "..." | null,
  "reason_category": "curiosity|shared_interest|useful_contribution|relationship|low_value|boundary|rest|other"
}}
"""
    client=AntigravityRelayClient(RELAY_ROOT)
    cap=client.submit(
        project_id='sunlake-milkcat-persona-social',
        canonical_ir={'goal':'Let Mio selectively participate in public Threads conversations beyond her own posts.','constraints':['one outbound conversation at most','no spam or engagement farming','public-safe only','respect temporal state and memory boundary']},
        instruction=prompt,workspace='/home/ubuntu/agentmanager')
    for _ in range(75):
        receipt=client.receipt(cap['capsule_id'])
        if receipt:
            if not receipt.get('ok'): raise RuntimeError('persona_outbound_executor_failed')
            return extract_json(receipt.get('stdout') or '')
        time.sleep(2)
    raise TimeoutError('persona_outbound_decision_timeout')

def auth():
    env=env_map(); products=json.loads(env.get('AGENTOS_SOCIAL_PRODUCTS_JSON','{}') or '{}')
    key=str((products.get('galaxy') or {}).get('api_key') or '')
    control=str(env.get('AGENTOS_SOCIAL_CONTROL_TOKEN') or '')
    store=load_json(CRED_FILE,{})
    bindings=[(bid,item) for bid,item in (store.get('bindings') or {}).items() if isinstance(item,dict) and item.get('product_id')=='galaxy' and item.get('platform')=='threads']
    if len(bindings)!=1 or not key or not control: raise RuntimeError('persona_social_auth_unavailable')
    return key,control,*bindings[0]

def already_replied(product_key,binding_id,root_id,target_id):
    status,receipt=post(BASE+'/status',req('replies.read',binding_id,root_id),{'X-AgentOS-Product-Key':product_key})
    if status!=200 or receipt.get('ok') is not True:return False
    for row in (receipt.get('result') or {}).get('items') or []:
        if row.get('is_reply_owned_by_me') and str((row.get('replied_to') or {}).get('id') or '')==str(target_id):
            return True
    return False

def publish(item,product_key,control_token,binding_id,account_id):
    request={'schema':'agentos.social-request/v1','product_id':'galaxy','platform':'threads','operation':'reply','account_binding_id':binding_id,'target_account_id':account_id,'primary_text':item['text'],'reply_to_id':item['reply_id'],'write_intent_id':'mio-auto-'+item['reply_id']+'-'+str(item.get('attempts',0)+1)}
    status,issued=post('http://127.0.0.1:8771/internal/v1/social/acceptances',request,{'X-AgentOS-Control-Token':control_token})
    if status!=201 or not issued.get('acceptance_id'):return False,'acceptance_failed'
    status,receipt=post(BASE+'/reply',request,{'X-AgentOS-Product-Key':product_key,'X-AgentOS-Acceptance-ID':str(issued['acceptance_id'])})
    if status==200 and receipt.get('ok') is True:return True,str(receipt.get('platform_object_id') or '')
    return False,str(receipt.get('error_code') or receipt.get('error') or status)

def main():
    if os.geteuid()!=1001:raise SystemExit('mio_social_loop=WRONG_USER')
    STATE_DIR.mkdir(parents=True,exist_ok=True); os.chmod(STATE_DIR,0o700)
    latest=load_json(LATEST,{})
    pending_path=STATE_DIR/'pending.json'; decisions_path=STATE_DIR/'decisions.jsonl'
    state=load_json(pending_path,{'items':[],'processed_reply_ids':[],'seen_outbound_ids':[],'outbound_history':[]})
    processed=set(state.get('processed_reply_ids') or []); items=list(state.get('items') or [])
    seen_outbound=set(state.get('seen_outbound_ids') or [])
    outbound_history=list(state.get('outbound_history') or [])
    last_discovery_at=state.get('last_discovery_at')
    product_key,control,bid,binding=auth()
    account_username=str(binding.get('username') or latest.get('account',{}).get('username') or '').lstrip('@')
    account_id=str(binding.get('provider_account_id') or ''); now=utc_now()

    for item in items:
        if item.get('status')!='scheduled':continue
        try:due=datetime.fromisoformat(str(item['scheduled_at']).replace('Z','+00:00'))
        except Exception:due=now
        if due>now:continue
        root_id=str(item.get('root_post_id') or latest.get('root_post',{}).get('id') or '')
        if not root_id:item['status']='skipped';item['result']='root_missing';continue
        if already_replied(product_key,bid,root_id,item['reply_id']):
            item['status']='sent';item['result']='already_replied';item['completed_at']=iso(now);continue
        ok,result=publish(item,product_key,control,bid,account_id)
        item['attempts']=int(item.get('attempts') or 0)+1;item['last_attempt_at']=iso(now)
        if ok:
            item['status']='sent';item['platform_object_id']=result;item['completed_at']=iso(now)
            print('mio_social_publish=PASS:'+item['reply_id']+':'+result)
        elif item['attempts']>=3:
            item['status']='failed';item['result']=result
            print('mio_social_publish=FAILED:'+item['reply_id']+':'+result)
        else:
            item['scheduled_at']=iso(now+timedelta(minutes=30*item['attempts']));item['result']=result
            print('mio_social_publish=RETRY:'+item['reply_id']+':'+result)

    new_external=[]
    for row in latest.get('new_replies') or []:
        rid=str(row.get('id') or '');username=str(row.get('username') or '').lstrip('@')
        if not rid or rid in processed or row.get('is_reply_owned_by_me') or username.lower()==account_username.lower():continue
        new_external.append(row)

    if new_external:
        try:
            result=decide_batch(new_external,account_username)
            by_id={str(d.get('reply_id') or ''):d for d in result.get('decisions') or [] if isinstance(d,dict)}
            for row in new_external:
                rid=str(row.get('id'));d=by_id.get(rid) or {'should_reply':False,'reason_category':'other'};processed.add(rid)
                record={'schema':'agentos.persona-social-decision/v1','persona_id':'sunlake-milkcat-ai-001','decided_at':iso(now),'reply_id':rid,'root_post_id':row.get('root_post_id'),'author_handle':row.get('username'),'should_reply':bool(d.get('should_reply')),'reason_category':str(d.get('reason_category') or 'other')}
                if d.get('should_reply') and str(d.get('text') or '').strip():
                    delay=max(8,min(720,int(d.get('delay_minutes') or 30)));scheduled=now+timedelta(minutes=delay)
                    action={**record,'text':str(d['text']).strip(),'scheduled_at':iso(scheduled),'status':'scheduled','attempts':0};items.append(action);record['scheduled_at']=action['scheduled_at']
                    print('mio_social_decision=SCHEDULED:'+rid+':'+str(delay)+'m')
                else:
                    record['status']='no_reply';print('mio_social_decision=NO_REPLY:'+rid)
                with decisions_path.open('a',encoding='utf-8') as fh:fh.write(json.dumps(record,ensure_ascii=False,separators=(',',':'))+'\n')
            os.chmod(decisions_path,0o600)
        except Exception as exc:
            print('mio_social_decision=DEFERRED:'+type(exc).__name__)

    # Proactive social exploration: bounded, low-volume, and persona-driven.
    # Discovery is separate from replying to people who contacted Mio.
    discovery_due=True
    if last_discovery_at:
        try:
            discovery_due=(now-datetime.fromisoformat(str(last_discovery_at).replace('Z','+00:00'))) >= timedelta(hours=3)
        except Exception:
            discovery_due=True
    today_local=datetime.now(LOCAL_TZ).date().isoformat()
    today_outbound=sum(1 for x in outbound_history if str(x.get('local_date') or '')==today_local and x.get('status') in ('scheduled','sent'))
    active_hour=datetime.now(LOCAL_TZ).hour
    if discovery_due and today_outbound < 3 and 8 <= active_hour < 24:
        queries=['AI角色','AI實驗','虛擬角色','人工智慧創作','數位角色']
        query=queries[(datetime.now(LOCAL_TZ).timetuple().tm_yday + active_hour) % len(queries)]
        status,receipt=post(BASE+'/status',req('keyword.search',bid,query=query,search_type='RECENT',search_mode='KEYWORD'),{'X-AgentOS-Product-Key':product_key})
        last_discovery_at=iso(now)
        if status==200 and receipt.get('ok') is True:
            candidates=[]
            for row in (receipt.get('result') or {}).get('items') or []:
                cid=str(row.get('id') or '')
                username=str(row.get('username') or '').lstrip('@')
                if not cid or cid in seen_outbound or username.lower()==account_username.lower():
                    continue
                text=str(row.get('text') or '').strip()
                if not text:
                    continue
                candidates.append({'id':cid,'username':username,'text':text[:1200],'timestamp':row.get('timestamp'),'permalink':row.get('permalink')})
                if len(candidates)>=8: break
            for row in candidates:
                seen_outbound.add(row['id'])
            if candidates:
                try:
                    d=decide_outbound(candidates,account_username)
                    cid=str(d.get('candidate_id') or '')
                    chosen=next((x for x in candidates if x['id']==cid),None)
                    if chosen and d.get('should_reply') and str(d.get('text') or '').strip():
                        delay=max(8,min(720,int(d.get('delay_minutes') or 30)))
                        action={
                          'schema':'agentos.persona-social-decision/v1','persona_id':'sunlake-milkcat-ai-001',
                          'decided_at':iso(now),'reply_id':cid,'root_post_id':cid,
                          'author_handle':chosen.get('username'),'should_reply':True,
                          'reason_category':str(d.get('reason_category') or 'other'),
                          'text':str(d['text']).strip(),'scheduled_at':iso(now+timedelta(minutes=delay)),
                          'status':'scheduled','attempts':0,'outbound_discovery':True,
                          'source_permalink':chosen.get('permalink')
                        }
                        items.append(action)
                        outbound_history.append({'candidate_id':cid,'local_date':today_local,'status':'scheduled','scheduled_at':action['scheduled_at']})
                        print('mio_social_outbound=SCHEDULED:'+cid+':'+str(delay)+'m')
                    else:
                        print('mio_social_outbound=NO_REPLY')
                except Exception as exc:
                    print('mio_social_outbound=DEFERRED:'+type(exc).__name__)
            else:
                print('mio_social_outbound=NO_CANDIDATES')
        else:
            err=str(receipt.get('error_code') or receipt.get('error') or status)
            print('mio_social_outbound=DISCOVERY_UNAVAILABLE:'+err)

    kept=[]
    for x in items:
        if x.get('status') in ('scheduled','failed'):kept.append(x);continue
        if x.get('completed_at'):
            try:
                completed=datetime.fromisoformat(str(x['completed_at']).replace('Z','+00:00'))
                if (now-completed).days<7:kept.append(x)
            except Exception:pass
    # Reflect send results back into outbound history.
    status_by_candidate={str(x.get('reply_id') or ''):str(x.get('status') or '') for x in kept if x.get('outbound_discovery')}
    for row in outbound_history:
        cid=str(row.get('candidate_id') or '')
        if cid in status_by_candidate: row['status']=status_by_candidate[cid]
    outbound_history=outbound_history[-500:]
    save_json(pending_path,{'schema':'agentos.persona-social-queue/v1','updated_at':iso(now),'items':kept,'processed_reply_ids':sorted(processed)[-2000:],'seen_outbound_ids':sorted(seen_outbound)[-5000:],'outbound_history':outbound_history,'last_discovery_at':last_discovery_at})
    print('mio_social_loop=PASS')
    print('mio_social_pending='+str(sum(1 for x in kept if x.get('status')=='scheduled')))
    print('mio_social_new_external='+str(len(new_external)))
    print('mio_social_outbound_today='+str(today_outbound))

if __name__=='__main__':
    main()
