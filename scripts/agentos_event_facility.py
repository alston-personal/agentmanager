#!/usr/bin/env python3
"""Reusable, declarative, read-only-to-the-world stochastic event facility.

Event definitions belong to subscribers. This module NEVER posts, replies,
executes subscriber-supplied code, or modifies a persona's permanent IR.
The transport/wake adapter remains an independent integration responsibility.
"""
import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SCHEMA="agentos.event.subscription/v1"
ENGINE_VERSION="agentos.event-facility/stochastic-v1"
ALLOWED_DELIVERY={"next_cycle","immediate","batch","record_only"}
ALLOWED_EFFECTS={"energy_delta","mood_delta","initiative_modifier"}
ALLOWED_SEVERITY={"minor","moderate","major"}

def validate_subscription(config):
    if not isinstance(config,dict) or config.get("schema")!=SCHEMA:
        raise ValueError("EVENT_SUBSCRIPTION_SCHEMA")
    if not isinstance(config.get("subscription_id"),str) or not config["subscription_id"]:
        raise ValueError("EVENT_SUBSCRIPTION_ID")
    if not isinstance(config.get("target"),str) or not config["target"].startswith(("persona:","worker:","app:")):
        raise ValueError("EVENT_TARGET")
    trigger=config.get("trigger") or {}
    if trigger.get("kind")!="stochastic" or trigger.get("model")!="daily_count":
        raise ValueError("EVENT_TRIGGER_UNSUPPORTED")
    p=trigger.get("probability_per_day")
    if isinstance(p,bool) or not isinstance(p,(float,int)) or not 0<=p<=1:
        raise ValueError("EVENT_PROBABILITY")
    max_count=trigger.get("max_events_per_day")
    if type(max_count)!=int or not 0<=max_count<=12:
        raise ValueError("EVENT_DAILY_LIMIT")
    min_gap=trigger.get("min_gap_hours")
    if isinstance(min_gap,bool) or not isinstance(min_gap,(int,float)) or not 0<=min_gap<=24:
        raise ValueError("EVENT_GAP")
    ZoneInfo(trigger.get("timezone","UTC"))
    if config.get("delivery",{}).get("mode") not in ALLOWED_DELIVERY:
        raise ValueError("EVENT_DELIVERY_MODE")
    definitions=config.get("definitions") or []
    if not isinstance(definitions,list) or not definitions or len(definitions)>32:
        raise ValueError("EVENT_DEFINITIONS")
    ids=set()
    for event in definitions:
        if not isinstance(event,dict) or not isinstance(event.get("id"),str) or not event["id"] or event["id"] in ids:
            raise ValueError("EVENT_DEFINITION_ID")
        ids.add(event["id"])
        if not isinstance(event.get("summary"),str) or not 0<len(event["summary"])<=240:
            raise ValueError("EVENT_DEFINITION_SUMMARY")
        if event.get("fictional") is not True and config["target"].startswith("persona:"):
            raise ValueError("EVENT_PERSONA_FICTION_BOUNDARY")
        effects=event.get("temporary_effect") or {}
        if not isinstance(effects,dict) or set(effects)-ALLOWED_EFFECTS:
            raise ValueError("EVENT_EFFECT_NOT_ALLOWED")
        for name,delta in effects.items():
            if isinstance(delta,bool) or not isinstance(delta,(int,float)) or not -12<=delta<=12:
                raise ValueError("EVENT_EFFECT_RANGE")
    sev=config.get("severity_distribution") or {}
    if not isinstance(sev,dict) or set(sev)-ALLOWED_SEVERITY or not any(
        isinstance(v,(int,float)) and not isinstance(v,bool) and v>0 for v in sev.values()):
        raise ValueError("EVENT_SEVERITY")
    return config

def evaluate(config, at, existing=()):
    """Produce due candidate occurrences and a reproducible draw receipt.

    Deterministic, subscriber-scoped daily draw with 0/1/2 event counts;
    candidates have fixed scheduled timestamps, so replays dedupe by ID.
    Caller persists events atomically, then hands deliveries to its governed
    event transport. A roll is not automatically an event or a delivery.
    """
    validate_subscription(config)
    if at.tzinfo is None:
        raise ValueError("EVENT_TIMEZONE_REQUIRED")
    trigger=config["trigger"]
    local=at.astimezone(ZoneInfo(trigger.get("timezone","UTC")))
    day=local.date().isoformat()
    seed=int(hashlib.sha256(
        (config["subscription_id"]+"|"+day+"|"+ENGINE_VERSION).encode()).hexdigest()[:16],16)
    rng=random.Random(seed)
    max_count=trigger["max_events_per_day"]
    occurs=rng.random()<trigger["probability_per_day"]
    count=(rng.randint(1,max_count) if occurs and max_count>0 else 0)
    definitions=config["definitions"]
    weights=config["severity_distribution"]
    levels=[k for k in ("minor","moderate","major") if weights.get(k,0)>0]
    earliest_hour=int(trigger.get("earliest_hour",8))
    if not 0<=earliest_hour<=23:
        raise ValueError("EVENT_EARLIEST_HOUR")
    gap=trigger["min_gap_hours"]
    slots=[]
    # A common minute preserves the configured minimum spacing across slots.
    daily_minute=rng.randrange(0,60)
    for index in range(count):
        # Fixed allocation within local day; do not claim a 24h continuous Poisson process.
        target_hour=earliest_hour+index*gap
        if target_hour>=24:
            break
        scheduled=local.replace(hour=int(target_hour),minute=daily_minute,second=0,microsecond=0)
        slots.append((index,scheduled))
    seen={x.get("id") for x in existing if isinstance(x,dict)}
    emitted=[]
    for index,scheduled in slots:
        definition=definitions[rng.randrange(len(definitions))]
        level=rng.choices(levels,weights=[weights[k] for k in levels],k=1)[0]
        eid=hashlib.sha256(
            (config["subscription_id"]+"|"+day+"|"+str(index)).encode()).hexdigest()[:24]
        if local<scheduled or "evt-"+eid in seen:
            continue
        emitted.append({
            "id":"evt-"+eid,"type":"persona.stochastic_event" if config["target"].startswith("persona:") else "facility.stochastic_event",
            "schema":"agentos.event.occurrence/v1","subscription_id":config["subscription_id"],
            "target":config["target"],"local_date":day,
            # Event cursor uses actual committed-emission time; scheduled_at is
            # informational. A delayed carrier must not make a newly emitted
            # occurrence look older than the subscriber's event cursor.
            "timestamp":at.astimezone(timezone.utc).isoformat().replace("+00:00","Z"),
            "scheduled_at":scheduled.astimezone(timezone.utc).isoformat().replace("+00:00","Z"),
            "category":definition["id"],"severity":level,"summary":definition["summary"],
            "temporary_effect":definition.get("temporary_effect",{}),
            "fictional_character_event":bool(definition.get("fictional")),
            "real_world_observation":False,"ir_adoption_allowed":False,"reply_allowed":False,
            "delivery_policy":config["delivery"]["mode"],
            "source":"agentos.event_facility","generator_version":ENGINE_VERSION,
            "seed":seed
        })
    return {"schema":"agentos.event.draw-receipt/v1",
            "subscription_id":config["subscription_id"],"local_date":day,
            "seed":seed,"planned_count":len(slots),"due_emitted":len(emitted),
            "status":"DRAWN" if slots else "NO_EVENT",
            "events":emitted}

def main():
    import argparse
    from pathlib import Path
    ap=argparse.ArgumentParser()
    ap.add_argument("--persona-dir",required=True)
    ap.add_argument("--subscription",required=True)
    ap.add_argument("--receipt-out")
    args=ap.parse_args()
    root=Path(args.persona_dir).resolve()
    subscription=(root/args.subscription).resolve()
    if not subscription.is_relative_to(root) or not subscription.is_file() or subscription.is_symlink():
        raise SystemExit("EVENT_SUBSCRIPTION_PATH_INVALID")
    config=json.loads(subscription.read_text(encoding="utf-8"))
    if config.get("target")!="persona:"+root.name:
        raise SystemExit("EVENT_SUBSCRIPTION_TARGET_MISMATCH")
    ledger=root/"events/events.jsonl"
    existing=[]
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                row=json.loads(line)
                if isinstance(row,dict): existing.append(row)
            except (ValueError,TypeError):
                continue
    result=evaluate(config,datetime.now(timezone.utc),existing)
    if result["events"]:
        # Durable delivery intent is persisted in the SAME canonical data repo
        # transaction as the occurrence. It is not a platform-write grant.
        pending=root/"pdca/event_deliveries"
        pending.mkdir(parents=True,exist_ok=True)
        for event in result["events"]:
            path=pending/(event["id"]+".json")
            if not path.exists():
                path.write_text(json.dumps({
                    "schema":"agentos.event.delivery-receipt/v1",
                    "event_id":event["id"],"subscription_id":event["subscription_id"],
                    "target":event["target"],"status":"PENDING_WAKE",
                    "delivery_policy":event["delivery_policy"],
                    "emitted_at":event["timestamp"],"ack_cycle":None
                },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        ledger.parent.mkdir(parents=True,exist_ok=True)
        with ledger.open("a",encoding="utf-8") as out:
            for event in result["events"]:
                out.write(json.dumps(event,ensure_ascii=False,separators=(",",":"))+"\n")
    if args.receipt_out:
        receipt_path=Path(args.receipt_out).resolve()
        if not receipt_path.is_relative_to(root):
            raise SystemExit("EVENT_RECEIPT_PATH_INVALID")
        receipt_path.parent.mkdir(parents=True,exist_ok=True)
        receipt_path.write_text(json.dumps({
            k:v for k,v in result.items() if k!="events"
        },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="events"},ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
