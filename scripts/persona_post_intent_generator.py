#!/usr/bin/env python3
import argparse, glob, hashlib, json, os, random, re, subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

def load(path):
    with open(path,"r",encoding="utf-8") as f:
        return json.load(f)

def read_events(path,limit=80):
    out=[]
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value=json.loads(line)
            if isinstance(value,dict):
                out.append(value)
        except Exception:
            pass
    return out[-limit:]

def discover_executor():
    patterns=[
      "/home/ubuntu/.antigravity-ide-server/extensions/anthropic.claude-code-*-linux-arm64/resources/native-binary/claude",
      "/home/ubuntu/.antigravity-ide-server/extensions/anthropic.claude-code-*/resources/native-binary/claude",
    ]
    found=[]
    for pattern in patterns:
        found += glob.glob(pattern)
    for path in sorted(set(found),reverse=True):
        if os.path.isfile(path) and os.access(path,os.X_OK):
            return [path,"--bare","--print","--output-format","text","--effort","low"]
    return None

def extract_json(text):
    text=text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m=re.search(r"\{.*\}",text,re.S)
    if not m:
        raise ValueError("executor_json_missing")
    return json.loads(m.group(0))

def safe_post_text(text):
    if not isinstance(text,str):
        return False
    s=text.strip()
    if not s or len(s)>500:
        return False
    if "http://" in s or "https://" in s:
        return False
    if len(re.findall(r"[😀-🙏🌀-🫿]",s))>3:
        return False
    return True

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--persona-dir",required=True)
    args=ap.parse_args()
    root=Path(args.persona_dir)
    state=load(root/"pdca/state.json")
    ir=load(root/"ir/current.json")
    persona=load(root/"persona_state.json")
    cfg=load(root/"pdca/config.json")
    events=read_events(root/"events/events.jsonl")

    growth=cfg.get("growth_mode",{}) if isinstance(cfg.get("growth_mode"),dict) else {}
    now_utc=datetime.now(timezone.utc)
    todays_posts=[]
    for e in events:
        if e.get("type") not in ("post.sent","post.published"): continue
        ts=str(e.get("timestamp") or "")
        try:
            dt=datetime.fromisoformat(ts.replace("Z","+00:00"))
        except Exception:
            continue
        if dt.astimezone().date()==now_utc.astimezone().date():
            todays_posts.append(dt.astimezone(timezone.utc))
    todays_posts.sort()
    max_posts=int(growth.get("daily_post_max",3))
    min_gap=int(growth.get("minimum_post_gap_minutes",240))
    if len(todays_posts)>=max_posts:
        print(json.dumps({"status":"NO_POST","reason":"daily_post_max_reached","posts_today":len(todays_posts)},ensure_ascii=False))
        return 0
    if todays_posts:
        gap=(now_utc-todays_posts[-1]).total_seconds()/60.0
        if gap < min_gap:
            print(json.dumps({"status":"DEFER","reason":"minimum_post_gap","gap_minutes":round(gap,1),"required":min_gap},ensure_ascii=False))
            return 0

    pending=list(state.get("pending_external_actions") or [])
    consider=next((x for x in pending if isinstance(x,dict) and x.get("capability")=="social.post.consider" and x.get("status")=="candidate"),None)
    if not consider:
        print(json.dumps({"status":"NO_CANDIDATE"},ensure_ascii=False))
        return 0
    if any(x.get("capability")=="social.post.publish" and x.get("status") in ("candidate","in_progress") for x in pending if isinstance(x,dict)):
        print(json.dumps({"status":"SKIP","reason":"post_publish_already_pending"},ensure_ascii=False))
        return 0

    activity_ref=str(state.get("last_activity_receipt") or "")
    activity={}
    if activity_ref:
        p=root/activity_ref
        if p.exists():
            activity=load(p)

    recent=[]
    for e in events[-50:]:
        if e.get("type") not in ("post.sent","post.published","reply.observed","reply.sent","wardrobe.window_shopping","pdca.activity.completed"):
            continue
        recent.append({
          "type":e.get("type"),
          "timestamp":e.get("timestamp"),
          "text":str(e.get("text") or e.get("summary") or "")[:500],
          "author":e.get("author_handle") or e.get("username"),
          "source_object_id":e.get("source_object_id") or e.get("object_id")
        })

    executor=discover_executor()
    if not executor:
        print(json.dumps({"status":"DEFER","reason":"persona_reasoning_executor_unavailable"},ensure_ascii=False))
        return 0

    contract={
      "current_ir":{
        "ir_id":ir.get("ir_id"),
        "current_self":ir.get("current_self"),
        "reply_contract":ir.get("reply_contract"),
        "promoted_growth":ir.get("promoted_growth")
      },
      "persona":{
        "voice":persona.get("voice"),
        "autonomy":persona.get("autonomy"),
        "temporal_behavior":persona.get("temporal_behavior"),
        "energy":persona.get("energy")
      },
      "pdca":{
        "cycle":state.get("cycle"),
        "focus":state.get("current_focus"),
        "consider_reason":consider.get("reason"),
        "activity_receipt":activity
      },
      "growth_mode":growth,
      "growth_context":{
        "posts_today":len(todays_posts),
        "daily_target":int(growth.get("daily_post_target",2)),
        "daily_max":max_posts,
        "minimum_gap_minutes":min_gap
      },
      "recent_verified_events":recent
    }

    prompt="""You are deciding whether Mio should publish one routine Threads post now.
The JSON context below is authoritative. Do not invent real-world experiences, locations, purchases, photos, meetings, weather, feelings caused by events, or relationship history that are not supported by the context.
A post may be based on verified recent events, a clearly labeled internal reflection, a question, or a small thought. Avoid repetitive generic inspirational copy.
When growth_mode.enabled is true and phase is reach_first, optimize for qualified discovery: the opening should contain a concrete hook, contrast, tension, surprising angle, or very easy-to-answer question. Prefer topic lanes that already have interaction evidence. Do not use clickbait that misrepresents the content. Do not write like a marketer. The post must still sound like Mio.
Mio is allowed to make routine public posts autonomously under policy, but commercial claims, payments, contracts, identity changes, private data, or unsupported real-world claims require no post.
Use natural Traditional Chinese. Keep it concise and human-like. Use 0-2 emoji unless the content strongly benefits from more. Do not mention internal systems, IR, PDCA, policies, or that a model generated the text.
Return ONLY one JSON object with exactly these keys:
{"should_post":true|false,"human_required":true|false,"reason":"short internal reason","post_text":"public text or empty"}
Context:
"""+json.dumps(contract,ensure_ascii=False)

    result=subprocess.run([*executor,prompt],cwd="/home/ubuntu/agentmanager",text=True,capture_output=True,timeout=90)
    if result.returncode!=0:
        print(json.dumps({"status":"DEFER","reason":"reasoning_executor_failed","returncode":result.returncode},ensure_ascii=False))
        return 0
    try:
        decision=extract_json(result.stdout)
    except Exception as e:
        print(json.dumps({"status":"DEFER","reason":"invalid_reasoning_output","detail":type(e).__name__},ensure_ascii=False))
        return 0

    should=bool(decision.get("should_post"))
    human=bool(decision.get("human_required"))
    text=str(decision.get("post_text") or "").strip()
    reason=str(decision.get("reason") or "")[:300]
    if human or not should:
        consider["status"]="completed"
        consider["completed_at"]=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
        consider["decision"]="no_post"
        consider["decision_reason"]=reason
        state["pending_external_actions"]=pending[-12:]
        tmp=root/"pdca/state.json.tmp"
        tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        os.replace(tmp,root/"pdca/state.json")
        print(json.dumps({"status":"NO_POST","human_required":human,"reason":reason},ensure_ascii=False))
        return 0
    if not safe_post_text(text):
        print(json.dumps({"status":"DEFER","reason":"post_text_guard_failed"},ensure_ascii=False))
        return 0

    now=datetime.now(timezone.utc)
    latency=persona.get("temporal_behavior",{}).get("post_latency",{}).get("typical_minutes",[5,25])
    try:
        lo,hi=int(latency[0]),int(latency[-1])
    except Exception:
        lo,hi=5,25
    seed=int(hashlib.sha256(f"{state.get('cycle')}|{ir.get('ir_id')}|{text}".encode()).hexdigest()[:16],16)
    rng=random.Random(seed)
    delay=rng.randint(max(3,lo),max(max(3,lo),hi))
    not_before=(now+timedelta(minutes=delay)).isoformat().replace("+00:00","Z")
    action_id=f"mio-post-c{state.get('cycle')}-{hashlib.sha256(text.encode()).hexdigest()[:10]}"
    action={
      "action_id":action_id,
      "cycle":state.get("cycle"),
      "capability":"social.post.publish",
      "status":"candidate",
      "policy":"routine_posts=autonomous_with_policy",
      "requires_real_adapter_receipt":True,
      "primary_text":text,
      "decision_reason":reason,
      "ir_id":ir.get("ir_id"),
      "not_before":not_before,
      "reasoning_executor":"antigravity_claude"
    }
    consider["status"]="completed"
    consider["completed_at"]=now.isoformat().replace("+00:00","Z")
    consider["decision"]="publish_candidate_created"
    consider["publish_action_id"]=action_id
    pending.append(action)
    state["pending_external_actions"]=pending[-12:]
    state["last_post_intent"]=action_id
    tmp=root/"pdca/state.json.tmp"
    tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.replace(tmp,root/"pdca/state.json")

    out=root/"pdca/post_intents"/f"{action_id}.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps({
      "schema":"agentos.persona-post-intent/v1",
      "created_at":now.isoformat().replace("+00:00","Z"),
      **action
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":"CANDIDATE_CREATED","action_id":action_id,"not_before":not_before},ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
