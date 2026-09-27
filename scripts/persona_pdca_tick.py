#!/usr/bin/env python3
import argparse, hashlib, json, os, random
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def dump_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)

def parse_ts(value):
    if not value:
        return None
    value = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None

def local_phase(now_local):
    mins = now_local.hour * 60 + now_local.minute
    def in_range(start_h, start_m, end_h, end_m):
        s = start_h*60 + start_m
        e = end_h*60 + end_m
        if s <= e:
            return s <= mins < e
        return mins >= s or mins < e
    if in_range(0,30,7,30): return "sleep"
    if in_range(12,30,13,30): return "rest"
    if in_range(7,30,9,30): return "morning_warmup"
    if in_range(9,30,12,30): return "high_focus"
    if in_range(13,30,16,30): return "afternoon"
    if in_range(16,30,19,30): return "social"
    if in_range(19,30,22,30): return "creative_social"
    if in_range(22,30,24,0) or in_range(0,0,0,30): return "late"
    return "idle"

def read_events(path):
    events = []
    if not path.exists():
        return events
    for line in path.read_text(encoding="utf-8").splitlines():
        line=line.strip()
        if not line: continue
        try: events.append(json.loads(line))
        except Exception: continue
    return events

def event_ts(e):
    for k in ("timestamp","created_at","occurred_at","generated_at","time"):
        if e.get(k):
            return parse_ts(str(e[k]))
    return None

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--persona-dir", required=True)
    ap.add_argument("--receipt-out")
    args=ap.parse_args()
    root=Path(args.persona_dir)
    persona=load_json(root/"persona_state.json")
    ir=load_json(root/"ir/current.json")
    cfg=load_json(root/"pdca/config.json")
    state_path=root/"pdca/state.json"
    state=load_json(state_path)
    events_path=root/"events/events.jsonl"

    if not cfg.get("enabled",False):
        print(json.dumps({"status":"DISABLED"},ensure_ascii=False)); return 0

    tz=ZoneInfo(cfg.get("timezone","Asia/Taipei"))
    now_utc=datetime.now(timezone.utc)
    now_local=now_utc.astimezone(tz)
    phase=local_phase(now_local)

    energy_cfg=persona.get("energy",{})
    capacity=float(energy_cfg.get("capacity",100))
    energy=float(state.get("energy_current",energy_cfg.get("current",50)))
    last_tick=parse_ts(state.get("last_tick_at"))
    if last_tick:
        elapsed_h=max(0.0,min((now_utc-last_tick.astimezone(timezone.utc)).total_seconds()/3600.0,12.0))
        if phase=="sleep":
            rate=float(energy_cfg.get("recovery",{}).get("sleep_points_per_hour",12))
        elif phase=="rest":
            rate=float(energy_cfg.get("recovery",{}).get("rest_points_per_hour",7))
        else:
            rate=float(energy_cfg.get("recovery",{}).get("awake_points_per_hour",3))
        energy=min(capacity,energy+elapsed_h*rate)

    events=read_events(events_path)
    since=parse_ts(state.get("last_event_timestamp"))
    unseen=[]; latest_event_ts=since
    for e in events:
        ts=event_ts(e)
        if ts and (latest_event_ts is None or ts>latest_event_ts): latest_event_ts=ts
        if since is None or (ts and ts>since): unseen.append(e)

    counts={}
    for e in unseen:
        typ=e.get("type","unknown"); counts[typ]=counts.get(typ,0)+1
    observed=counts.get("reply.observed",0)
    posted=counts.get("post.sent",0)+counts.get("post.published",0)
    wardrobe=counts.get("wardrobe.window_shopping",0)

    if phase=="sleep": candidates=[("sleep",1.0)]
    elif phase=="rest": candidates=[("rest",1.0)]
    else:
        candidates=[("observe",0.8)]
        if observed: candidates.append(("review_social_feedback",min(3.0,1.2+observed*0.25)))
        if phase in ("morning_warmup","high_focus") and energy>=35:
            candidates += [("wardrobe_plan",1.15 if wardrobe==0 else 0.55),("reflect",1.0)]
        if phase in ("high_focus","afternoon","creative_social","late") and energy>=40:
            candidates.append(("content_ideation",1.3 if posted==0 else 0.75))
        if state.get("consecutive_noops",0)>=2 and energy>=30:
            candidates.append(("reflect",1.4))
    if energy<15 and phase not in ("sleep","rest"):
        candidates=[("rest",1.0)]
    elif energy<30 and phase not in ("sleep","rest"):
        candidates=[(n,w) for n,w in candidates if n in ("observe","reflect","rest")] or [("rest",1.0)]

    cycle=int(state.get("cycle",0))+1
    seed_material=f"{cfg.get('persona_id')}|{ir.get('ir_id')}|{now_local:%Y-%m-%dT%H}|{cycle}|{state.get('consecutive_noops',0)}"
    seed=int(hashlib.sha256(seed_material.encode()).hexdigest()[:16],16)
    rng=random.Random(seed)
    selected=rng.choices([x[0] for x in candidates],weights=[x[1] for x in candidates],k=1)[0]

    costs=energy_cfg.get("action_costs",{})
    cost_map={"sleep":0,"rest":0,"observe":float(costs.get("observe_passive",0.2)),
              "review_social_feedback":float(costs.get("read_thread",1)),
              "reflect":1.5,"wardrobe_plan":2.0,"content_ideation":3.0}
    cost=min(energy,cost_map.get(selected,1.0))
    energy_after=max(0.0,energy-cost)
    do={"action":selected,"status":"completed_internal","energy_cost":cost}
    pending=list(state.get("pending_external_actions",[]))
    external=None
    if selected=="review_social_feedback" and observed:
        external={"capability":"social.reply.review","status":"candidate",
                  "reason":f"{observed} newly observed replies since last PDCA cursor",
                  "policy":"public_conversation=autonomous_with_policy","requires_real_adapter_receipt":True}
    elif selected=="content_ideation" and energy_after>=30:
        external={"capability":"social.post.consider","status":"candidate",
                  "reason":"active creative window with sufficient energy",
                  "policy":"routine_posts=autonomous_with_policy","requires_real_adapter_receipt":True}
    if external and not any(x.get("capability")==external["capability"] and x.get("status")=="candidate" for x in pending[-8:]):
        pending.append(external); pending=pending[-12:]

    noop=selected in ("sleep","rest","observe") and not unseen
    noops=int(state.get("consecutive_noops",0))+1 if noop else 0
    focus={"review_social_feedback":"relationships","content_ideation":"creative_output",
           "wardrobe_plan":"wardrobe","reflect":"self_model","observe":"environment",
           "rest":"recovery","sleep":"recovery"}[selected]

    receipt={"schema":"agentos.persona-pdca-receipt/v1","persona_id":cfg.get("persona_id"),
             "cycle":cycle,"tick_at":now_utc.isoformat().replace("+00:00","Z"),
             "local_time":now_local.isoformat(),"phase":phase,"ir_id":ir.get("ir_id"),"seed":seed,
             "plan":{"energy":round(energy,2),"unseen_events":len(unseen),"event_counts":counts,
                     "candidates":[{"intent":n,"weight":w} for n,w in candidates],"selected_intent":selected},
             "do":do,
             "check":{"internal_action_verified":True,"external_action_completed":False,
                      "new_event_counts":counts,"unseen_events":len(unseen),
                      "energy_before":round(energy,2),"energy_after":round(energy_after,2),
                      "policy_boundary_respected":True},
             "act":{"next_focus":focus,"consecutive_noops":noops,
                    "pending_external_actions":len(pending),"external_candidate":external},
             "truth_boundary":{"fabricated_external_completion":False,"external_receipt_required":True}}

    day=now_local.strftime("%Y-%m-%d")
    receipts=root/"pdca/receipts"/f"{day}.jsonl"
    receipts.parent.mkdir(parents=True,exist_ok=True)
    with open(receipts,"a",encoding="utf-8") as f:
        f.write(json.dumps(receipt,ensure_ascii=False,separators=(",",":"))+"\n")
    with open(events_path,"a",encoding="utf-8") as f:
        f.write(json.dumps({"id":f"pdca-{now_local:%Y%m%d-%H%M%S}-c{cycle}","type":"pdca.cycle",
                            "timestamp":receipt["tick_at"],"summary":f"PDCA cycle {cycle}: {selected} during {phase}",
                            "source":"persona_pdca_runtime","receipt_ref":str(receipts.relative_to(root)),
                            "external_action_completed":False},ensure_ascii=False,separators=(",",":"))+"\n")

    state.update({"cycle":cycle,"last_tick_at":receipt["tick_at"],
                  "last_action_at":receipt["tick_at"] if not noop else state.get("last_action_at"),
                  "last_ir_id":ir.get("ir_id"),"energy_current":round(energy_after,2),
                  "consecutive_noops":noops,
                  "last_event_timestamp":latest_event_ts.astimezone(timezone.utc).isoformat().replace("+00:00","Z") if latest_event_ts else state.get("last_event_timestamp"),
                  "current_focus":focus,"pending_external_actions":pending,
                  "last_receipt":str(receipts.relative_to(root)),"status":"RUNNING"})
    dump_json(state_path,state)
    if args.receipt_out: dump_json(Path(args.receipt_out),receipt)
    print(json.dumps(receipt,ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
