#!/usr/bin/env python3
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA_ROOT=Path("/home/ubuntu/agent-data")
PERSONA=DATA_ROOT/"personas/sunlake-milkcat"
OUT_PUBLIC=Path("/tmp/mio-observer-public.json")
OUT_OWNER=Path("/tmp/mio-observer-owner.json")

def load(path:Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

def main()->int:
    ir=load(PERSONA/"ir/current.json",{})
    pdca=load(PERSONA/"pdca/state.json",{})
    state=load(PERSONA/"persona_state.json",{})
    current_self=ir.get("current_self") or {}
    energy=(state.get("energy") or {}).get("current")
    status=str(pdca.get("status") or "UNKNOWN")
    focus=str(pdca.get("current_focus") or "unknown")
    current={
      "intent":"observe" if focus in ("recovery","unknown") else focus,
      "title":"持續觀察自己的世界" if focus in ("recovery","unknown") else "目前專注："+focus,
      "summary":"正在維持自主循環，等待新的互動、事件或值得投入的行動。",
      "focus_label":"focus · "+focus
    }
    public={
      "schema":"milkcat.mio-observer-public/v1",
      "updated_at":now_iso(),
      "updated_label":"最近更新",
      "persona_revision":ir.get("revision"),
      "activity_count":len(pdca.get("pending_external_actions") or []),
      "current":current,
      "energy_band":("充足" if isinstance(energy,(int,float)) and energy>=50 else "偏低" if isinstance(energy,(int,float)) and energy<30 else "普通"),
      "recent":[],
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
    capability_health={
      "persona.pdca":"degraded" if pdca_stale else "healthy",
      "social.metrics":"degraded" if latest_metric.get("status") in ("UNAVAILABLE","ERROR") else "healthy",
      "persona.relationship.memory":"healthy" if (PERSONA/"relationships").exists() else "unknown",
      "persona.observer.public":"healthy",
      "persona.observer.owner":"healthy",
    }
    public["health"]=capability_health
    public["last_heartbeat_at"]=latest_metric.get("timestamp") or pdca.get("last_tick_at")

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
    }
    OUT_PUBLIC.write_text(json.dumps(public,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    OUT_OWNER.write_text(json.dumps(owner,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("mio_observer_projection=PASS")
    print("mio_observer_public="+str(OUT_PUBLIC))
    print("mio_observer_owner="+str(OUT_OWNER))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
