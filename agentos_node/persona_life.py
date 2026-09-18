from __future__ import annotations
import json, math, os, random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA="agentos.persona-life-runtime/v1"

def _utc_now()->datetime:
    return datetime.now(timezone.utc)

def _iso(dt:datetime)->str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

def _load(path:Path, default:dict[str,Any])->dict[str,Any]:
    try:
        value=json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value,dict) else default
    except Exception:
        return default

def _save(path:Path,payload:dict[str,Any])->None:
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    os.chmod(tmp,0o600); tmp.replace(path); os.chmod(path,0o600)

def effective_energy(path:Path, config:dict[str,Any], now:datetime|None=None)->dict[str,Any]:
    now=now or _utc_now()
    cap=float(config.get("capacity",100))
    default=float(config.get("current",cap))
    state=_load(path,{"schema":SCHEMA,"energy":default,"last_energy_update_at":_iso(now),"events_today":[]})
    try:last=datetime.fromisoformat(str(state.get("last_energy_update_at") or "").replace("Z","+00:00"))
    except Exception:last=now
    hours=max(0.0,(now-last).total_seconds()/3600.0)
    recovery=config.get("recovery") or {}
    rate=float(recovery.get("awake_points_per_hour",3))
    state["energy"]=max(float(config.get("floor",0)),min(cap,float(state.get("energy",default))+hours*rate))
    state["last_energy_update_at"]=_iso(now)
    state["schema"]=SCHEMA
    _save(path,state)
    return state

def can_spend(path:Path, config:dict[str,Any], cost:float, reserve:float=0.0)->bool:
    state=effective_energy(path,config)
    return float(state.get("energy",0)) >= float(cost)+float(reserve)

def spend(path:Path, config:dict[str,Any], cost:float, *, reason:str, meta:dict[str,Any]|None=None)->dict[str,Any]:
    state=effective_energy(path,config)
    before=float(state.get("energy",0))
    floor=float(config.get("floor",0))
    after=max(floor,before-max(0.0,float(cost)))
    state["energy"]=after
    ledger=list(state.get("energy_ledger") or [])
    ledger.append({"at":_iso(_utc_now()),"reason":reason,"cost":round(float(cost),3),"before":round(before,3),"after":round(after,3),"meta":meta or {}})
    state["energy_ledger"]=ledger[-500:]
    _save(path,state)
    return state

def apply_delta(path:Path, config:dict[str,Any], delta:float, *, reason:str)->dict[str,Any]:
    state=effective_energy(path,config)
    cap=float(config.get("capacity",100)); floor=float(config.get("floor",0))
    before=float(state.get("energy",0))
    state["energy"]=max(floor,min(cap,before+float(delta)))
    ledger=list(state.get("energy_ledger") or [])
    ledger.append({"at":_iso(_utc_now()),"reason":reason,"delta":round(float(delta),3),"before":round(before,3),"after":round(float(state["energy"]),3)})
    state["energy_ledger"]=ledger[-500:]
    _save(path,state)
    return state

EVENTS=[
 {"id":"mood_bright","category":"mood_positive","text":"心情突然很好","effects":{"energy_delta":5,"mood_delta":0.25,"initiative_modifier":1.18},"hours":5},
 {"id":"mood_blue","category":"mood_negative","text":"突然有點憂傷","effects":{"energy_delta":-3,"mood_delta":-0.22,"reply_latency_modifier":1.25},"hours":6},
 {"id":"basketball","category":"activity","text":"跑去打了一場球","effects":{"energy_delta":-8,"mood_delta":0.18,"productivity_modifier":0.9},"hours":4,"min_energy":35},
 {"id":"creative_spark","category":"creative","text":"突然很想創作","effects":{"energy_delta":-2,"mood_delta":0.12,"initiative_modifier":1.3},"hours":5},
 {"id":"minor_sprain","category":"virtual_body_minor","text":"虛擬生活世界裡不小心扭到腳","effects":{"energy_delta":-6,"mood_delta":-0.12,"initiative_modifier":0.65},"hours":18,"min_energy":15},
 {"id":"frustrated","category":"frustration","text":"做事不太順，有點煩躁","effects":{"energy_delta":-4,"mood_delta":-0.16,"reply_latency_modifier":1.18},"hours":4},
 {"id":"serendipity","category":"serendipity","text":"偶然遇到一個讓她很感興趣的東西","effects":{"energy_delta":1,"mood_delta":0.16,"initiative_modifier":1.2},"hours":4}
]

def maybe_generate_event(path:Path, config:dict[str,Any], event_log:Path, now:datetime|None=None)->dict[str,Any]|None:
    now=now or _utc_now()
    state=effective_energy(path,{},now) if not config else _load(path,{"schema":SCHEMA,"energy":72,"last_energy_update_at":_iso(now),"events_today":[]})
    if not config.get("enabled",True): return None
    last_roll=state.get("last_event_roll_at")
    if last_roll:
        try:
            dt=datetime.fromisoformat(str(last_roll).replace("Z","+00:00"))
            if (now-dt).total_seconds()<3600:return None
        except Exception:pass
    state["last_event_roll_at"]=_iso(now)
    today=now.date().isoformat()
    recent=[e for e in (state.get("events_today") or []) if str(e.get("date"))==today]
    if len(recent)>=int(config.get("max_events_per_day",2)):
        state["events_today"]=recent; _save(path,state); return None
    if recent:
        try:
            last=datetime.fromisoformat(str(recent[-1]["at"]).replace("Z","+00:00"))
            if (now-last).total_seconds()<float(config.get("minimum_gap_hours",4))*3600:
                state["events_today"]=recent; _save(path,state); return None
        except Exception:pass
    daily=max(0.0,min(1.0,float(config.get("daily_event_probability",0.42))))
    hourly=1-math.pow(1-daily,1/24) if daily<1 else 1.0
    seed=random.SystemRandom().getrandbits(63)
    rng=random.Random(seed)
    if rng.random()>=hourly:
        state["events_today"]=recent; _save(path,state); return None
    energy=float(state.get("energy",72))
    eligible=[e for e in EVENTS if energy>=float(e.get("min_energy",0))]
    if not eligible:
        state["events_today"]=recent; _save(path,state); return None
    template=rng.choice(eligible)
    event={
      "schema":"agentos.persona-stochastic-event/v1","event_id":f"life-{now.strftime('%Y%m%dT%H%M%SZ')}-{seed:x}",
      "persona_id":"sunlake-milkcat-ai-001","world":"persona_world","category":template["category"],
      "template_id":template["id"],"summary":template["text"],"created_at":_iso(now),
      "random_seed":seed,"generator_version":"persona-life/v0.1","eligibility_context":{"energy":round(energy,2)},
      "effects":template["effects"],"duration_hours":template["hours"],"growth_evidence":False
    }
    delta=float((template.get("effects") or {}).get("energy_delta",0))
    state["energy"]=max(0.0,min(100.0,energy+delta))
    recent.append({"date":today,"at":_iso(now),"event_id":event["event_id"]})
    state["events_today"]=recent
    state["active_event"]=event
    _save(path,state)
    event_log.parent.mkdir(parents=True,exist_ok=True)
    with event_log.open("a",encoding="utf-8") as fh:fh.write(json.dumps(event,ensure_ascii=False,separators=(",",":"))+"\n")
    return event
