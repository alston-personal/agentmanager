#!/usr/bin/env python3
import argparse, json, os, random, hashlib
from datetime import datetime, timezone
from pathlib import Path

def load(p):
    with open(p,"r",encoding="utf-8") as f:return json.load(f)

def write_json(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+".tmp")
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.replace(tmp,p)

def latest_pdca(root):
    state=load(root/"pdca/state.json")
    receipt_path=root/state["last_receipt"]
    lines=[x for x in receipt_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return state,json.loads(lines[-1])

def wardrobe_plan(root,cycle,now):
    catalog=load(root/"wardrobe/catalog.json")
    items=[x for x in catalog.get("items",[]) if x.get("state") in ("candidate","approved","owned")]
    by={}
    for x in items: by.setdefault(x.get("category","other"),[]).append(x)
    seed=int(hashlib.sha256(f"wardrobe|{cycle}|{now[:10]}".encode()).hexdigest()[:16],16)
    rng=random.Random(seed)
    chosen=[]
    if by.get("dress"):
        dress=rng.choice(by["dress"])
        if rng.random()<0.35: chosen=[dress]
    if not chosen:
        if by.get("top"): chosen.append(rng.choice(by["top"]))
        if by.get("bottom"): chosen.append(rng.choice(by["bottom"]))
    if by.get("outerwear") and rng.random()<0.35: chosen.append(rng.choice(by["outerwear"]))
    if by.get("shoes") and rng.random()<0.5: chosen.append(rng.choice(by["shoes"]))
    return {
      "activity":"wardrobe_plan",
      "result":"virtual_outfit_proposal",
      "item_ids":[x.get("item_id") for x in chosen],
      "items":[{"item_id":x.get("item_id"),"category":x.get("category"),"label":x.get("label"),"state":x.get("state")} for x in chosen],
      "truth_boundary":{
        "claims_owned":all(x.get("state")=="owned" for x in chosen) if chosen else False,
        "claims_real_wear":False,
        "claims_real_purchase":False,
        "note":"This is a virtual styling proposal. Candidate retail items are not represented as owned or actually worn."
      }
    }

def reflect(root,receipt):
    counts=receipt.get("plan",{}).get("event_counts",{})
    focus=receipt.get("act",{}).get("next_focus")
    return {
      "activity":"reflect","result":"reflection_note",
      "reflection":{
        "focus":focus,
        "evidence_summary":counts,
        "observation":"Keep the next action grounded in recent evidence; no external event is assumed beyond recorded receipts."
      }
    }

def content_ideation(root,receipt):
    focus=receipt.get("act",{}).get("next_focus")
    return {
      "activity":"content_ideation","result":"content_seed",
      "seed":{
        "theme":focus or "daily_continuity",
        "angle":"Turn one verified recent event or internal reflection into a small, natural post idea.",
        "constraints":["no fabricated offline experience","avoid repetitive posting","publish only through the social write gate"]
      }
    }

def observe(root,receipt):
    return {
      "activity":"observe","result":"context_snapshot",
      "snapshot":{
        "phase":receipt.get("phase"),
        "event_counts":receipt.get("plan",{}).get("event_counts",{}),
        "unseen_events":receipt.get("plan",{}).get("unseen_events",0)
      }
    }

def rest(kind):
    return {"activity":kind,"result":"recovery","external_action":False}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--persona-dir",required=True)
    args=ap.parse_args()
    root=Path(args.persona_dir)
    state,receipt=latest_pdca(root)
    cycle=int(receipt["cycle"]); intent=receipt["plan"]["selected_intent"]
    now=datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
    if intent=="wardrobe_plan": result=wardrobe_plan(root,cycle,now)
    elif intent=="reflect": result=reflect(root,receipt)
    elif intent=="content_ideation": result=content_ideation(root,receipt)
    elif intent=="observe":
        result={"activity":intent,"result":"delegated_to_social_executor",
                "status":"pending_external","external_action":True,
                "action_id":receipt.get("do",{}).get("action_id")}
    elif intent in ("rest","sleep"): result=rest(intent)
    elif intent=="review_social_feedback":
        result={"activity":intent,"result":"delegated_to_social_executor"}
    else:
        result={"activity":intent,"result":"unsupported_internal_intent"}

    activity={
      "schema":"agentos.persona-activity-receipt/v1",
      "persona_id":state.get("persona_id"),"cycle":cycle,"created_at":now,
      "intent":intent,**result
    }
    day=receipt.get("local_time",now)[:10]
    out=root/"pdca/activities"/day/f"cycle-{cycle}.json"
    write_json(out,activity)
    state["last_activity_receipt"]=str(out.relative_to(root))
    write_json(root/"pdca/state.json",state)
    with open(root/"events/events.jsonl","a",encoding="utf-8") as f:
        f.write(json.dumps({
          "id":f"pdca-activity-c{cycle}-{intent}",
          "type":"pdca.activity.delegated" if intent=="observe" else "pdca.activity.completed","timestamp":now,
          "source":"persona_internal_activity_executor","cycle":cycle,"intent":intent,
          "receipt_ref":str(out.relative_to(root)),"result":activity.get("result")
        },ensure_ascii=False,separators=(",",":"))+"\n")
    print(json.dumps(activity,ensure_ascii=False))
    return 0

if __name__=="__main__": raise SystemExit(main())
