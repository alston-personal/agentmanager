from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA = "agentos.monitor/v1"
NOTIFICATION_SCHEMA = "agentos.notification/v1"
RECEIPT_SCHEMA = "agentos.monitor-receipt/v1"

OFFICIAL_SOURCES = {
    "google-ai-pro": "https://one.google.com/about/google-ai-plans/",
    "chatgpt-plus": "https://openai.com/chatgpt/pricing/",
}

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def iso(dt: datetime | None = None) -> str:
    return (dt or utcnow()).replace(microsecond=0).isoformat().replace("+00:00","Z")

def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z","+00:00")).astimezone(timezone.utc)

def parse_duration(value: str | int | float | None, default: int = 60) -> int:
    if value is None:
        return default
    if isinstance(value,(int,float)):
        return max(1,int(value))
    raw=str(value).strip().lower()
    units={"s":1,"m":60,"h":3600,"d":86400}
    if raw[-1:] in units:
        return max(1,int(float(raw[:-1])*units[raw[-1]]))
    return max(1,int(float(raw)))

def stable_digest(value: Any) -> str:
    raw=json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False)
    return "sha256:"+hashlib.sha256(raw.encode()).hexdigest()

def data_root() -> Path:
    return Path(os.environ.get("AGENT_DATA_ROOT") or "/home/ubuntu/agent-data")

@dataclass
class DispatchResult:
    ok: bool
    value: dict[str,Any]
    provenance: dict[str,Any]
    failure_class: str | None = None

class MonitorStore:
    def __init__(self,path: Path):
        self.path=path
        path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path)
        self.db.row_factory=sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS monitors(
          monitor_id TEXT PRIMARY KEY,
          spec_json TEXT NOT NULL,
          status TEXT NOT NULL,
          baseline_json TEXT,
          last_checked TEXT,
          last_changed TEXT,
          last_notified TEXT,
          next_due TEXT NOT NULL,
          dedupe_key TEXT,
          last_condition INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS receipts(
          receipt_id TEXT PRIMARY KEY,
          monitor_id TEXT NOT NULL,
          created_at TEXT NOT NULL,
          ok INTEGER NOT NULL,
          receipt_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notifications(
          notification_id TEXT PRIMARY KEY,
          monitor_id TEXT NOT NULL,
          severity TEXT NOT NULL,
          summary TEXT NOT NULL,
          observed_at TEXT NOT NULL,
          read INTEGER NOT NULL DEFAULT 0,
          resolved_at TEXT,
          dedupe_key TEXT,
          provenance_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_monitors_due ON monitors(status,next_due);
        CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(read,resolved_at);
        """)
        self.db.commit()

    def register(self,spec: dict[str,Any], *, replace: bool=False) -> dict[str,Any]:
        validate_spec(spec)
        mid=spec["monitor"]["id"]
        now=iso()
        schedule=spec["schedule"]
        next_due=now if schedule.get("run_immediately",True) else iso(utcnow()+timedelta(seconds=parse_duration(schedule.get("every"),60)))
        row=self.db.execute("SELECT monitor_id FROM monitors WHERE monitor_id=?",(mid,)).fetchone()
        if row and not replace:
            raise ValueError("monitor already exists")
        if row:
            self.db.execute("""UPDATE monitors SET spec_json=?,status='active',updated_at=?,next_due=? WHERE monitor_id=?""",
                (json.dumps(spec,ensure_ascii=False,sort_keys=True),now,next_due,mid))
        else:
            self.db.execute("""INSERT INTO monitors(monitor_id,spec_json,status,baseline_json,next_due,created_at,updated_at)
              VALUES(?,?, 'active', ?,?,?,?)""",
              (mid,json.dumps(spec,ensure_ascii=False,sort_keys=True),json.dumps(spec.get("baseline") or {},ensure_ascii=False,sort_keys=True),next_due,now,now))
        self.db.commit()
        return self.inspect(mid)

    def inspect(self,mid: str) -> dict[str,Any]:
        row=self.db.execute("SELECT * FROM monitors WHERE monitor_id=?",(mid,)).fetchone()
        if not row: raise KeyError(mid)
        out=dict(row); out["spec"]=json.loads(out.pop("spec_json")); out["baseline"]=json.loads(out.pop("baseline_json") or "{}")
        return out

    def list(self) -> list[dict[str,Any]]:
        return [self.inspect(r["monitor_id"]) for r in self.db.execute("SELECT monitor_id FROM monitors ORDER BY monitor_id")]

    def set_status(self,mid: str,status: str) -> None:
        if status not in {"active","paused"}: raise ValueError(status)
        cur=self.db.execute("UPDATE monitors SET status=?,updated_at=? WHERE monitor_id=?",(status,iso(),mid))
        if not cur.rowcount: raise KeyError(mid)
        self.db.commit()

    def delete(self,mid: str) -> None:
        self.db.execute("DELETE FROM monitors WHERE monitor_id=?",(mid,)); self.db.commit()

    def due(self,limit:int=50) -> list[str]:
        now=iso()
        return [r["monitor_id"] for r in self.db.execute(
          "SELECT monitor_id FROM monitors WHERE status='active' AND next_due<=? ORDER BY next_due LIMIT ?",(now,limit))]

    def record(self,mid:str, *, observed:dict[str,Any], dispatch:DispatchResult, triggered:bool, summary:str|None, severity:str, dedupe_key:str|None, cooldown_seconds:int) -> dict[str,Any]:
        row=self.inspect(mid); spec=row["spec"]; now=iso()
        baseline=row["baseline"]
        changed=stable_digest(observed)!=stable_digest(baseline)
        interval=parse_duration(spec["schedule"].get("every"),60)
        next_due=iso(utcnow()+timedelta(seconds=interval))
        notify=False
        if triggered:
            last=row.get("last_notified")
            cooldown_ok=(not last) or ((utcnow()-parse_iso(last)).total_seconds()>=cooldown_seconds)
            duplicate=False
            if dedupe_key:
                q=self.db.execute("""SELECT 1 FROM notifications WHERE monitor_id=? AND dedupe_key=? AND resolved_at IS NULL LIMIT 1""",(mid,dedupe_key)).fetchone()
                duplicate=q is not None
            notify=cooldown_ok and not duplicate
        receipt_payload={
          "schema":RECEIPT_SCHEMA,"monitor_id":mid,"observed_at":now,"ok":dispatch.ok,
          "executor_failure": None if dispatch.ok else dispatch.failure_class,
          "observation":observed if dispatch.ok else None,"condition_triggered":bool(triggered) if dispatch.ok else False,
          "notification_emitted":notify,"provenance":dispatch.provenance,
        }
        rid="monrec-"+hashlib.sha256((mid+now+stable_digest(receipt_payload)).encode()).hexdigest()[:20]
        receipt_payload["receipt_id"]=rid
        self.db.execute("INSERT INTO receipts VALUES(?,?,?,?,?)",(rid,mid,now,1 if dispatch.ok else 0,json.dumps(receipt_payload,ensure_ascii=False,sort_keys=True)))
        if dispatch.ok:
            self.db.execute("""UPDATE monitors SET baseline_json=?,last_checked=?,last_changed=?,last_notified=COALESCE(?,last_notified),
              next_due=?,dedupe_key=?,last_condition=?,updated_at=? WHERE monitor_id=?""",
              (json.dumps(observed,ensure_ascii=False,sort_keys=True),now,now if changed else row.get("last_changed"),
               now if notify else None,next_due,dedupe_key,1 if triggered else 0,now,mid))
            if not triggered and row.get("last_condition"):
                self.db.execute("UPDATE notifications SET resolved_at=? WHERE monitor_id=? AND resolved_at IS NULL",(now,mid))
            if notify and summary:
                nid="notify-"+hashlib.sha256((mid+str(dedupe_key)+now).encode()).hexdigest()[:20]
                prov={"monitor_receipt_id":rid,**dispatch.provenance}
                self.db.execute("""INSERT INTO notifications(notification_id,monitor_id,severity,summary,observed_at,read,resolved_at,dedupe_key,provenance_json)
                  VALUES(?,?,?,?,?,0,NULL,?,?)""",(nid,mid,severity,summary,now,dedupe_key,json.dumps(prov,sort_keys=True)))
        else:
            self.db.execute("UPDATE monitors SET last_checked=?,next_due=?,updated_at=? WHERE monitor_id=?",(now,next_due,now,mid))
        self.db.commit()
        return receipt_payload

    def notifications(self,unread_only:bool=True) -> list[dict[str,Any]]:
        sql="SELECT * FROM notifications"
        if unread_only: sql+=" WHERE read=0"
        sql+=" ORDER BY observed_at DESC"
        out=[]
        for row in self.db.execute(sql):
            d=dict(row); d["schema"]=NOTIFICATION_SCHEMA; d["read"]=bool(d["read"]); d["provenance"]=json.loads(d.pop("provenance_json")); out.append(d)
        return out

def validate_spec(spec:dict[str,Any]) -> None:
    if spec.get("schema") not in (None,SCHEMA): raise ValueError("unsupported monitor schema")
    spec["schema"]=SCHEMA
    mid=str((spec.get("monitor") or {}).get("id") or "")
    if not mid or len(mid)>96 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for c in mid):
        raise ValueError("invalid monitor id")
    sched=spec.get("schedule") or {}
    parse_duration(sched.get("every"),60)
    exe=spec.get("execution") or {}
    cap=str(exe.get("capability") or "")
    if cap not in {"node.realm.inspect","agentos.scheduler.status","agentos.relay.status","threads.dm.login.probe","web.official.snapshot"}:
        raise ValueError("monitor capability is not registered")
    if cap=="web.official.snapshot":
        src=str((spec.get("payload") or {}).get("source") or "")
        if src not in OFFICIAL_SOURCES: raise ValueError("official source is not allowlisted")

def official_snapshot(source:str) -> DispatchResult:
    url=OFFICIAL_SOURCES[source]
    req=urllib.request.Request(url,headers={"User-Agent":"AgentOS-Monitor/1.0","Accept":"text/html,application/xhtml+xml"})
    try:
        with urllib.request.urlopen(req,timeout=12) as r:
            raw=r.read(2_000_000)
            final=str(r.geturl())
        if not final.startswith("https://"): raise RuntimeError("non-https redirect rejected")
        text=raw.decode("utf-8","replace")
        compact=" ".join(text.split())
        obs={"source":source,"url":final,"content_sha256":hashlib.sha256(compact.encode()).hexdigest(),"content_bytes":len(raw)}
        return DispatchResult(True,obs,{"capability":"web.official.snapshot","source":source,"authority":"monitor-runtime-allowlist"})
    except Exception as exc:
        return DispatchResult(False,{},{"capability":"web.official.snapshot","source":source},exc.__class__.__name__)

def one_dispatch(capability:str, operation:str, payload:dict[str,Any], source_commit:str) -> DispatchResult:
    base=os.environ.get("AGENTOS_RUNNER_WINDOW_BASE","http://127.0.0.1:8765")
    token=os.environ.get("AGENTOS_CONTROLLER_TOKEN","")
    if not token:
        return DispatchResult(False,{},{"capability":capability,"operation":operation},"AUTH_REQUIRED")
    body=json.dumps({"schema":"agentos.runner-window-dispatch/v1","capability":capability,"operation":operation,"source_commit":source_commit,"payload":payload}).encode()
    try:
        req=urllib.request.Request(base.rstrip("/")+"/v1/dispatch",data=body,method="POST",headers={"Authorization":"Bearer "+token,"Content-Type":"application/json"})
        with urllib.request.urlopen(req,timeout=12) as r: submit=json.load(r)
        request_id=submit["request_id"]
        deadline=time.time()+60
        while time.time()<deadline:
            req=urllib.request.Request(base.rstrip("/")+"/v1/dispatch/requests/"+request_id,headers={"Authorization":"Bearer "+token})
            with urllib.request.urlopen(req,timeout=12) as r: status=json.load(r)
            if status.get("state")=="completed":
                receipt=status.get("receipt") or {}
                ok=receipt.get("ok") is True
                return DispatchResult(ok,receipt,{"capability":capability,"operation":operation,"one_request_id":request_id},None if ok else str(receipt.get("failure_class") or "EXECUTOR_FAILED"))
            time.sleep(1)
        return DispatchResult(False,{},{"capability":capability,"operation":operation,"one_request_id":request_id},"TIMEOUT")
    except Exception as exc:
        return DispatchResult(False,{},{"capability":capability,"operation":operation},exc.__class__.__name__)

def parse_marker(receipt:dict[str,Any], prefix:str) -> str|None:
    for line in receipt.get("stdout_lines") or []:
        if isinstance(line,str) and line.startswith(prefix):
            return line.split("=",1)[1]
    return None

def execute(spec:dict[str,Any],source_commit:str) -> DispatchResult:
    cap=spec["execution"]["capability"]; payload=spec.get("payload") or {}
    if cap=="web.official.snapshot":
        return official_snapshot(str(payload["source"]))
    mapping={
      "node.realm.inspect":("node.realm","inspect"),
      "agentos.scheduler.status":("agentos.scheduler","status"),
      "agentos.relay.status":("agentos.relay","status"),
      "threads.dm.login.probe":("threads.dm","login.probe"),
    }
    public,op=mapping[cap]
    return one_dispatch(public,op,payload,source_commit)

def evaluate(spec:dict[str,Any], row:dict[str,Any], dispatch:DispatchResult) -> tuple[bool,str|None,str,str|None]:
    if not dispatch.ok:
        return False,None,"info",None
    cap=spec["execution"]["capability"]; cond=spec.get("condition") or {}; severity=str((spec.get("notification_policy") or {}).get("severity","medium"))
    old=row.get("baseline") or {}; new=dispatch.value
    if cap=="node.realm.inspect":
        state=parse_marker(new,"realm_node_status=") or "unknown"
        prev=parse_marker(old,"realm_node_status=") if isinstance(old,dict) else None
        bad=state in {"offline","degraded","stale","unknown"}
        triggered=bad and state!=prev
        return triggered,(f"{spec['monitor']['id']}: node state {prev or 'unknown'} -> {state}" if triggered else None),severity,f"state:{state}" if bad else None
    if cap=="agentos.scheduler.status":
        status=parse_marker(new,"scheduler_status=") or "unknown"
        triggered=status not in {"ok","healthy","PASS"}
        return triggered,(f"AgentOS scheduler status: {status}" if triggered else None),severity,f"scheduler:{status}" if triggered else None
    if cap=="agentos.relay.status":
        status=parse_marker(new,"relay_status=") or "unknown"
        triggered=status not in {"ok","healthy","PASS"}
        return triggered,(f"ONE relay status: {status}" if triggered else None),severity,f"relay:{status}" if triggered else None
    if cap=="threads.dm.login.probe":
        status=parse_marker(new,"threads_web_dm_login=") or parse_marker(new,"threads_dm_login=") or "unknown"
        triggered=status=="AUTH_REQUIRED"
        return triggered,("Threads session requires login" if triggered else None),severity,"threads:AUTH_REQUIRED" if triggered else None
    if cap=="web.official.snapshot":
        initialized=bool(row.get("last_checked"))
        changed=stable_digest(new)!=stable_digest(row.get("baseline") or {})
        triggered=initialized and changed
        label=str((spec.get("goal") or {}).get("description") or spec["monitor"]["id"])
        return triggered,(f"Official source changed: {label}" if triggered else None),severity,(f"official:{new.get('source')}:{new.get('content_sha256')}" if triggered else None)
    return False,None,severity,None

def run_monitor(store:MonitorStore,mid:str,source_commit:str) -> dict[str,Any]:
    row=store.inspect(mid); spec=row["spec"]
    result=execute(spec,source_commit)
    triggered,summary,severity,dedupe_key=evaluate(spec,row,result)
    policy=spec.get("notification_policy") or {}
    return store.record(mid,observed=result.value,dispatch=result,triggered=triggered,summary=summary,severity=severity,dedupe_key=dedupe_key,cooldown_seconds=parse_duration(policy.get("cooldown"),1800))

def tick(store:MonitorStore,source_commit:str) -> list[dict[str,Any]]:
    return [run_monitor(store,mid,source_commit) for mid in store.due()]

def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser()
    p.add_argument("--db",default=str(data_root()/ "runtime/monitor-runtime/monitor.sqlite3"))
    p.add_argument("--source-commit",default=os.environ.get("AGENTOS_SOURCE_COMMIT",""))
    sub=p.add_subparsers(dest="cmd",required=True)
    s=sub.add_parser("register"); s.add_argument("spec")
    s=sub.add_parser("inspect"); s.add_argument("monitor_id")
    sub.add_parser("list")
    s=sub.add_parser("pause"); s.add_argument("monitor_id")
    s=sub.add_parser("resume"); s.add_argument("monitor_id")
    s=sub.add_parser("delete"); s.add_argument("monitor_id")
    s=sub.add_parser("run"); s.add_argument("monitor_id")
    sub.add_parser("tick")
    sub.add_parser("notifications")
    a=p.parse_args(argv); store=MonitorStore(Path(a.db))
    if a.cmd=="register":
        spec=json.loads(Path(a.spec).read_text(encoding="utf-8")); out=store.register(spec)
    elif a.cmd=="inspect": out=store.inspect(a.monitor_id)
    elif a.cmd=="list": out=store.list()
    elif a.cmd=="pause": store.set_status(a.monitor_id,"paused"); out=store.inspect(a.monitor_id)
    elif a.cmd=="resume": store.set_status(a.monitor_id,"active"); out=store.inspect(a.monitor_id)
    elif a.cmd=="delete": store.delete(a.monitor_id); out={"deleted":a.monitor_id}
    elif a.cmd=="run":
        if not a.source_commit: raise SystemExit("source commit required")
        out=run_monitor(store,a.monitor_id,a.source_commit)
    elif a.cmd=="tick":
        if not a.source_commit: raise SystemExit("source commit required")
        out=tick(store,a.source_commit)
    else: out=store.notifications()
    print(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True))
    return 0

if __name__=="__main__": raise SystemExit(main())
