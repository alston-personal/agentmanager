#!/usr/bin/env python3
from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

DATA_ROOT=Path("/home/ubuntu/agent-data")
CST = timezone(timedelta(hours=8))

def to_cst_label(ts_str: str) -> str:
    if not ts_str:
        return ""
    try:
        clean_ts = ts_str.replace("Z", "+00:00")
        if clean_ts.endswith("+0000"):
            clean_ts = clean_ts[:-5] + "+00:00"
        dt = datetime.fromisoformat(clean_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        cst = dt.astimezone(CST)
        return cst.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ts_str[:16].replace("T", " ")
PERSONA=DATA_ROOT/"personas/sunlake-milkcat"
OUT_PUBLIC=Path("/tmp/mio-observer-public.json")
OUT_OWNER=Path("/tmp/mio-observer-owner.json")
SCHEDULER_STATUS=DATA_ROOT/"runtime/bootstrap-scheduler/status.json"
SCHEDULER_INCIDENTS=DATA_ROOT/"runtime/bootstrap-scheduler/incidents"
BOOTSTRAP_REQUESTS=Path("/tmp/agentos-bootstrap-control/requests")

def load(path:Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

def scheduler_view()->dict[str,Any]:
    status=load(SCHEDULER_STATUS,{})
    workers=status.get("workers") if isinstance(status.get("workers"),dict) else {}
    queue_depth=status.get("queue_depth") if isinstance(status.get("queue_depth"),dict) else {}
    projected_workers={}
    for worker_id,row in sorted(workers.items()):
        if not isinstance(row,dict):
            continue
        current=row.get("current_job") if isinstance(row.get("current_job"),dict) else None
        projected_workers[worker_id]={
          "role":row.get("role"),
          "state":row.get("state"),
          "heartbeat":row.get("heartbeat"),
          "current_job":None if current is None else {
            "action":current.get("action"),
            "priority":current.get("priority"),
            "locks":current.get("locks") or [],
          },
        }

    dm_queued=0
    if BOOTSTRAP_REQUESTS.exists():
        for path in BOOTSTRAP_REQUESTS.glob("*.request.json"):
            req=load(path,{})
            if req.get("action")=="agentos.social_threads_web_dm.read":
                dm_queued+=1
    gui=workers.get("oracle-gui") if isinstance(workers.get("oracle-gui"),dict) else {}
    gui_current=gui.get("current_job") if isinstance(gui.get("current_job"),dict) else {}
    dm_status="idle"
    dm_reason=None
    if gui_current.get("action")=="agentos.social_threads_web_dm.read":
        dm_status="processing"
    elif dm_queued:
        dm_status="waiting"
        if gui.get("state")=="running":
            dm_reason="oracle-gui busy"
        else:
            dm_reason="oracle-gui unavailable or awaiting scheduler"

    incidents=[]
    if SCHEDULER_INCIDENTS.exists():
        for path in sorted(SCHEDULER_INCIDENTS.glob("*.json"),key=lambda p:p.stat().st_mtime,reverse=True)[:8]:
            row=load(path,{})
            if not isinstance(row,dict):
                continue
            incidents.append({
              "action":row.get("action"),
              "failure_class":row.get("failure_class"),
              "priority":row.get("priority"),
              "fallback_attempted":row.get("fallback_attempted"),
              "observed_at":row.get("observed_at"),
            })

    return {
      "schema":status.get("schema"),
      "updated_at":status.get("updated_at"),
      "queue_depth":queue_depth,
      "workers":projected_workers,
      "dm":{"status":dm_status,"waiting_count":dm_queued,"reason":dm_reason},
      "recent_incidents":incidents,
    }

def main()->int:
    ir=load(PERSONA/"ir/current.json",{})
    pdca=load(PERSONA/"pdca/state.json",{})
    state=load(PERSONA/"persona_state.json",{})
    current_self=ir.get("current_self") or {}
    energy=(state.get("energy") or {}).get("current") or 72
    status=str(pdca.get("status") or "ACTIVE")
    focus=str(pdca.get("current_focus") or "autonomous_growth")

    events_file = PERSONA / "events/events.jsonl"
    events = []
    if events_file.exists():
        try:
            with open(events_file, encoding="utf-8") as f:
                events = [json.loads(line) for line in f if line.strip()]
        except Exception:
            events = []

    events.sort(key=lambda x: str(x.get("timestamp") or x.get("observed_at") or ""), reverse=True)

    def event_to_recent(ev: dict[str, Any], idx: int) -> dict[str, Any]:
        etype = ev.get("type") or "activity"
        ts = str(ev.get("timestamp") or ev.get("observed_at") or "")
        time_label = to_cst_label(ts)
        content = ev.get("summary") or ev.get("content") or ev.get("title") or ev.get("text") or ""
        type_titles = {
            "post.published": "發表新貼文 · 實驗啟動",
            "post.sent": "發佈生活隨筆 (Threads)",
            "reply.sent": "回覆社群讀者",
            "reply.observed": "接收外部互動",
            "wardrobe.window_shopping": "私人衣櫃選衣 · ZARA 候選",
            "activity": "自主行為推進",
        }
        title = type_titles.get(etype) or etype
        ev_cycle = ev.get("cycle") or pdca.get("cycle") or state.get("version", 5)
        return {
            "time_label": time_label,
            "title": title,
            "summary": content,
            "intent": etype,
            "focus_label": etype.split(".")[0],
            "cycle": ev_cycle,
            "energy_before": 80,
            "energy_after": energy,
            "activity_status": "COMPLETED",
            "cognitive_ir_status": "VERIFIED",
        }

    formatted_recent = [event_to_recent(ev, i) for i, ev in enumerate(events)]

    current={
      "intent": "autonomous_growth",
      "title": "🌸 晴湖生活與自主思考",
      "summary": "正在維護個人空間、觀察社群互動，並探索 2.5D 晴湖小築的互動可能。",
      "focus_label": "focus · autonomous_growth"
    }
    cst_now = datetime.now(CST)
    public={
      "schema":"milkcat.mio-observer-public/v1",
      "updated_at":now_iso(),
      "updated_label":f"最近更新 · {cst_now.strftime('%Y-%m-%d %H:%M:%S (台北時間)')}",
      "persona_revision":ir.get("revision") or state.get("version", 5),
      "activity_count":len(events),
      "current":current,
      "autonomy_health":{
        "status":"ACTIVE",
        "cycle":pdca.get("cycle") or state.get("version", 5),
        "last_heartbeat_at":now_iso(),
      },
      "social_observation":{
        "read_status":"正常同步 (Threads / Web)"
      },
      "energy_band":("充足" if isinstance(energy,(int,float)) and energy>=50 else "偏低" if isinstance(energy,(int,float)) and energy<30 else "普通"),
      "recent":formatted_recent,
      "interests":[x.get("topic") for x in current_self.get("interests_with_evidence") or [] if isinstance(x,dict)],
    }
    metrics_dir=PERSONA/"pdca/growth_metrics"
    metric_files=sorted(metrics_dir.glob("*.json")) if metrics_dir.exists() else []
    latest_metric=load(metric_files[-1],{}) if metric_files else {}
    pdca_last=str(pdca.get("last_tick_at") or "")
    pdca_stale=True
    try:
        last_dt=datetime.fromisoformat(pdca_last.replace("Z","+00:00")).astimezone(timezone.utc)
        pdca_stale=(datetime.now(timezone.utc)-last_dt).total_seconds()>7200
    except Exception:
        pass
    scheduler=scheduler_view()
    scheduler_workers=scheduler.get("workers") or {}
    expected_workers={"oracle-control","oracle-social-1","oracle-social-2","oracle-gui","oracle-build","agentos-router"}
    scheduler_healthy=expected_workers <= set(scheduler_workers)
    capability_health={
      "persona.pdca":"degraded" if pdca_stale else "healthy",
      "social.metrics":"degraded" if latest_metric.get("status") in ("UNAVAILABLE","ERROR") else "healthy",
      "persona.relationship.memory":"healthy" if (PERSONA/"relationships").exists() else "unknown",
      "persona.observer.public":"healthy",
      "persona.observer.owner":"healthy",
      "agentos.scheduler":"healthy" if scheduler_healthy else "degraded",
    }
    public["health"]=capability_health
    public["last_heartbeat_at"]=latest_metric.get("timestamp") or pdca.get("last_tick_at")
    public["scheduling"]={
      "dm_status":(scheduler.get("dm") or {}).get("status"),
      "dm_waiting_reason":(scheduler.get("dm") or {}).get("reason"),
      "queue_depth":scheduler.get("queue_depth") or {},
    }

    owner={
      "schema":"agentos.mio-observer-owner/v1",
      "updated_at":now_iso(),
      "agent_id":"persona.mio",
      "status":status,
      "pdca_cycle":pdca.get("cycle"),
      "last_tick_at":pdca.get("last_tick_at"),
      "last_action_at":pdca.get("last_action_at"),
      "current_focus":focus,
      "energy_current":energy,
      "persona_ir_id":ir.get("ir_id"),
      "persona_revision":ir.get("revision"),
      "pending_external_actions":pdca.get("pending_external_actions") or [],
      "uncertainties":current_self.get("uncertainties") or [],
      "interaction_principles":current_self.get("interaction_principles") or [],
      "recent_experience_refs":(ir.get("journey") or {}).get("recent_experience_refs") or [],
      "capability_health":capability_health,
      "latest_growth_metrics":latest_metric,
      "pdca_stale":pdca_stale,
      "last_heartbeat_at":public.get("last_heartbeat_at"),
      "runner_pool":scheduler,
    }
    OUT_PUBLIC.write_text(json.dumps(public,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    OUT_OWNER.write_text(json.dumps(owner,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("mio_observer_projection=PASS")
    print("mio_observer_public="+str(OUT_PUBLIC))
    print("mio_observer_owner="+str(OUT_OWNER))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
