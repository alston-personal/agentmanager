import json
from pathlib import Path
from agentos_node.monitor_runtime import MonitorStore, DispatchResult, evaluate, stable_digest

def spec(mid="x"):
    return {"schema":"agentos.monitor/v1","monitor":{"id":mid},"goal":{"description":"x"},
      "schedule":{"every":"5m"},"execution":{"capability":"node.realm.inspect"},
      "payload":{"node_id":"vopc5750"},"notification_policy":{"severity":"high","cooldown":"30m"}}

def test_register_is_durable(tmp_path):
    db=tmp_path/"m.sqlite3"; s=MonitorStore(db); s.register(spec("vopc")); s.db.close()
    s2=MonitorStore(db); assert s2.inspect("vopc")["status"]=="active"

def test_executor_failure_never_becomes_condition(tmp_path):
    s=MonitorStore(tmp_path/"m.sqlite3"); row=s.register(spec("vopc"))
    t,summary,sev,key=evaluate(row["spec"],row,DispatchResult(False,{},{},"TIMEOUT"))
    assert t is False and summary is None and key is None

def test_dedupe_and_resolve(tmp_path):
    s=MonitorStore(tmp_path/"m.sqlite3"); s.register(spec("vopc"))
    bad=DispatchResult(True,{"stdout_lines":["realm_node_status=offline"]},{"one_request_id":"r1"})
    row=s.inspect("vopc"); trig,summary,sev,key=evaluate(row["spec"],row,bad); assert trig
    s.record("vopc",observed=bad.value,dispatch=bad,triggered=trig,summary=summary,severity=sev,dedupe_key=key,cooldown_seconds=1800)
    assert len(s.notifications())==1
    good=DispatchResult(True,{"stdout_lines":["realm_node_status=online"]},{"one_request_id":"r2"})
    s.record("vopc",observed=good.value,dispatch=good,triggered=False,summary=None,severity="high",dedupe_key=None,cooldown_seconds=1800)
    n=s.notifications()[0]; assert n["resolved_at"] is not None

def test_official_baseline_does_not_notify_first_run(tmp_path):
    sp={"schema":"agentos.monitor/v1","monitor":{"id":"plan"},"goal":{"description":"plan"},
      "schedule":{"every":"7d"},"execution":{"capability":"web.official.snapshot"},"payload":{"source":"chatgpt-plus"},
      "notification_policy":{"severity":"medium","cooldown":"7d"}}
    s=MonitorStore(tmp_path/"m.sqlite3"); row=s.register(sp)
    d=DispatchResult(True,{"source":"chatgpt-plus","content_sha256":"x"},{"capability":"web.official.snapshot"})
    trig,*_=evaluate(sp,row,d); assert not trig
