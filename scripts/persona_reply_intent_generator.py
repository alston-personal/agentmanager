#!/usr/bin/env python3
import argparse, glob, hashlib, json, os, random, re, subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

def load(p):
    with open(p,"r",encoding="utf-8") as f: return json.load(f)

def read_events(path):
    out=[]
    if not path.exists(): return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            v=json.loads(line)
            if isinstance(v,dict): out.append(v)
        except Exception: pass
    return out

def discover_executor():
    patterns=[
      "/home/ubuntu/.antigravity-ide-server/extensions/anthropic.claude-code-*-linux-arm64/resources/native-binary/claude",
      "/home/ubuntu/.antigravity-ide-server/extensions/anthropic.claude-code-*/resources/native-binary/claude",
    ]
    found=[]
    for p in patterns: found += glob.glob(p)
    for p in sorted(set(found),reverse=True):
        if os.path.isfile(p) and os.access(p,os.X_OK):
            return [p,"--bare","--print","--output-format","text","--effort","low"]
    return None

def normalize_ts(v):
    if not v: return None
    try: return datetime.fromisoformat(str(v).replace("Z","+00:00"))
    except Exception: return None

def already_replied(events, reply):
    rid=str(reply.get("object_id") or reply.get("source_object_id") or "")
    root=str(reply.get("root_post_id") or reply.get("root_id") or "")
    ts=normalize_ts(reply.get("timestamp"))
    for e in events:
        if e.get("type")!="reply.sent": continue
        ets=normalize_ts(e.get("timestamp"))
        if ts and ets and ets <= ts: continue
        parent=str(e.get("parent_object_id") or e.get("reply_to_id") or "")
        eroot=str(e.get("root_post_id") or "")
        if rid and parent==rid: return True
        if root and eroot==root and ets and ts and ets>ts: return True
    return False

def root_text(events,root_id):
    for e in reversed(events):
        oid=str(e.get("object_id") or e.get("source_object_id") or "")
        if oid==root_id and e.get("type") in ("post.sent","post.published"):
            return str(e.get("text") or e.get("summary") or "").strip()
    return ""

def prior_thread(events,root_id,limit=8):
    rows=[]
    for e in events:
        if str(e.get("root_post_id") or e.get("root_id") or "")!=root_id: continue
        if e.get("type") not in ("reply.observed","reply.sent"): continue
        rows.append({
          "type":e.get("type"),"author":e.get("author_handle") or e.get("username"),
          "text":str(e.get("text") or e.get("summary") or "")[:500],
          "timestamp":e.get("timestamp")
        })
    return rows[-limit:]

def relationship_context(events,handle,limit=8):
    rows=[]
    for e in events:
        h=str(e.get("author_handle") or e.get("username") or "")
        if h.lower()!=handle.lower(): continue
        if e.get("type") not in ("reply.observed","reply.sent"): continue
        rows.append({"type":e.get("type"),"text":str(e.get("text") or e.get("summary") or "")[:400],"timestamp":e.get("timestamp")})
    return rows[-limit:]

def extract_json(text):
    text=text.strip()
    try: return json.loads(text)
    except Exception: pass
    m=re.search(r'\{.*\}',text,re.S)
    if not m: raise ValueError("executor_json_missing")
    return json.loads(m.group(0))

def safe_reply_text(text):
    if not isinstance(text,str): return False
    s=text.strip()
    if not s or len(s)>320: return False
    if "http://" in s or "https://" in s: return False
    if len(re.findall(r'[😀-🙏🌀-🫿]',s))>2: return False
    return True

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--persona-dir",required=True)
    args=ap.parse_args()
    root=Path(args.persona_dir)
    state=load(root/"pdca/state.json")
    ir=load(root/"ir/current.json")
    policy=load(root/"reply_policy.json")
    stances=load(root/"social_stances.json")
    persona=load(root/"persona_state.json")
    events=read_events(root/"events/events.jsonl")
    now=datetime.now(timezone.utc)

    # Only consider externally authored observed replies, newest first.
    observed=[]
    for e in events:
        if e.get("type")!="reply.observed": continue
        if str(e.get("actor") or "")==str(state.get("persona_id")): continue
        txt=str(e.get("text") or e.get("summary") or "").strip()
        if not txt: continue
        if already_replied(events,e): continue
        observed.append(e)
    observed.sort(key=lambda e: normalize_ts(e.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)

    pending=list(state.get("pending_external_actions") or [])
    if any(x.get("status") in ("candidate","in_progress") and x.get("capability")=="social.reply.send" for x in pending if isinstance(x,dict)):
        print(json.dumps({"status":"SKIP","reason":"reply_send_already_pending"},ensure_ascii=False)); return 0
    if not observed:
        print(json.dumps({"status":"NO_CANDIDATE"},ensure_ascii=False)); return 0

    candidate=observed[0]
    reply_id=str(candidate.get("object_id") or candidate.get("source_object_id") or "")
    root_id=str(candidate.get("root_post_id") or candidate.get("root_id") or "")
    handle=str(candidate.get("author_handle") or candidate.get("username") or "unknown")
    text=str(candidate.get("text") or candidate.get("summary") or "").strip()
    root_post=root_text(events,root_id)
    thread=prior_thread(events,root_id)
    relationship=relationship_context(events,handle)

    # Fail closed if required conversation context is unavailable.
    if not reply_id or not root_id or not root_post:
        print(json.dumps({"status":"DEFER","reason":"missing_required_thread_context","reply_id":reply_id},ensure_ascii=False)); return 0

    executor=discover_executor()
    if not executor:
        print(json.dumps({"status":"DEFER","reason":"persona_reasoning_executor_unavailable"},ensure_ascii=False)); return 0

    contract={
      "current_ir":{"ir_id":ir.get("ir_id"),"current_self":ir.get("current_self"),"reply_contract":ir.get("reply_contract"),"promoted_growth":ir.get("promoted_growth")},
      "reply_policy":policy,
      "social_stances":stances,
      "voice":persona.get("voice"),
      "autonomy":persona.get("autonomy"),
      "thread":{"root_post":root_post,"incoming_reply":{"id":reply_id,"author":handle,"text":text},"recent_thread":thread},
      "relationship_context":relationship
    }
    prompt="""You are deciding whether Mio should reply to one public Threads comment.
The JSON context below is authoritative. Do not invent biography, facts, purchases, locations, or relationship history.
First decide Mio's private position: agree, partly_agree, disagree, uncertain, playful_only, or no_reply.
Only propose a public reply when context is sufficient and replying is useful. Hostile bait may be no_reply. Legal/payment/contracts/private data must be no_reply and human_required=true.
Keep the public reply short, natural Traditional Chinese, consistent with Mio's current IR. Do not mention internal systems/policies. Do not overuse emoji (0-2 max).
Return ONLY one JSON object with exactly these keys:
{"position":"...","should_reply":true|false,"human_required":true|false,"reason":"short internal reason","reply_text":"public text or empty"}
Context:
"""+json.dumps(contract,ensure_ascii=False)

    try:
        p=subprocess.run([*executor,prompt],cwd="/home/ubuntu/agentmanager",text=True,capture_output=True,timeout=90)
    except subprocess.TimeoutExpired:
        print(json.dumps({"status":"DEFER","reason":"persona_reasoning_timeout","timeout_seconds":90},ensure_ascii=False))
        return 0
    if p.returncode!=0:
        print(json.dumps({"status":"DEFER","reason":"reasoning_executor_failed","returncode":p.returncode},ensure_ascii=False)); return 0
    try: decision=extract_json(p.stdout)
    except Exception as e:
        print(json.dumps({"status":"DEFER","reason":"invalid_reasoning_output","detail":type(e).__name__},ensure_ascii=False)); return 0

    allowed_positions={"agree","partly_agree","disagree","uncertain","playful_only","no_reply"}
    position=str(decision.get("position") or "")
    should=bool(decision.get("should_reply"))
    human=bool(decision.get("human_required"))
    reply_text=str(decision.get("reply_text") or "").strip()
    if position not in allowed_positions:
        print(json.dumps({"status":"DEFER","reason":"invalid_position"},ensure_ascii=False)); return 0
    if human or position=="no_reply" or not should:
        print(json.dumps({"status":"NO_REPLY","position":position,"human_required":human,"reason":str(decision.get("reason") or "")[:300]},ensure_ascii=False)); return 0
    if not safe_reply_text(reply_text):
        print(json.dumps({"status":"DEFER","reason":"reply_text_guard_failed"},ensure_ascii=False)); return 0

    # Respect Mio's configured reply latency instead of replying instantly by default.
    latency=persona.get("temporal_behavior",{}).get("reply_latency",{}).get("typical_minutes",[8,45])
    lo,hi=int(latency[0]),int(latency[-1])
    seed=int(hashlib.sha256(f"{reply_id}|{state.get('cycle')}|{ir.get('ir_id')}".encode()).hexdigest()[:16],16)
    rng=random.Random(seed)
    delay=rng.randint(max(3,lo),max(max(3,lo),hi))
    not_before=(now+timedelta(minutes=delay)).isoformat().replace("+00:00","Z")
    action_id=f"mio-reply-{reply_id}-{hashlib.sha256((reply_text+str(state.get('cycle'))).encode()).hexdigest()[:10]}"
    action={
      "action_id":action_id,"cycle":state.get("cycle"),"capability":"social.reply.send","status":"candidate",
      "policy":"public_conversation=autonomous_with_policy","requires_real_adapter_receipt":True,
      "reply_to_id":reply_id,"root_post_id":root_id,"target_handle":handle,"primary_text":reply_text,
      "position":position,"decision_reason":str(decision.get("reason") or "")[:300],
      "ir_id":ir.get("ir_id"),"not_before":not_before,"reasoning_executor":"antigravity_claude"
    }
    pending.append(action)
    state["pending_external_actions"]=pending[-12:]
    state["last_reply_intent"]=action_id
    tmp=root/"pdca/state.json.tmp"
    tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.replace(tmp,root/"pdca/state.json")
    out=root/"pdca/reply_intents"/f"{action_id}.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps({"schema":"agentos.persona-reply-intent/v1","created_at":now.isoformat().replace("+00:00","Z"),**action},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":"CANDIDATE_CREATED","action_id":action_id,"position":position,"not_before":not_before},ensure_ascii=False))
    return 0

if __name__=="__main__": raise SystemExit(main())
