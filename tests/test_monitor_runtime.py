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


def test_parse_marker_reads_step_stdout():
    from agentos_node.monitor_runtime import parse_marker
    receipt={"steps":[{"stdout":"x=1\nrealm_node_status=online\n"}]}
    assert parse_marker(receipt,"realm_node_status=")=="online"

def test_gateway_502_is_condition_not_executor_failure(tmp_path):
    from agentos_node.monitor_runtime import evaluate
    sp={"schema":"agentos.monitor/v1","monitor":{"id":"gw"},"goal":{"description":"gw"},
      "schedule":{"every":"5m"},"execution":{"capability":"agentos.gateway.health"},
      "payload":{},"notification_policy":{"severity":"high","cooldown":"30m"}}
    s=MonitorStore(tmp_path/"m.sqlite3"); row=s.register(sp)
    d=DispatchResult(True,{"http_status":502,"schema":None},{"capability":"agentos.gateway.health"})
    trig,summary,sev,key=evaluate(sp,row,d)
    assert trig is True
    assert "502" in summary
    assert key=="gateway:http:502"

def test_gui_completed_smoke_failure_is_health_condition(tmp_path):
    from agentos_node.monitor_runtime import evaluate
    sp={"schema":"agentos.monitor/v1","monitor":{"id":"gui"},"goal":{"description":"gui"},
      "schedule":{"every":"15m"},"execution":{"capability":"browser.gui.smoke"},
      "payload":{},"notification_policy":{"severity":"high","cooldown":"30m"}}
    s=MonitorStore(tmp_path/"m.sqlite3"); row=s.register(sp)
    d=DispatchResult(True,{"ok":False,"steps":[{"stdout":"oracle_gui_browser_smoke=FAIL"}]},
                     {"capability":"browser.gui","operation":"smoke","one_request_id":"r","probe_ok":False})
    trig,summary,sev,key=evaluate(sp,row,d)
    assert trig is True and key=="gui-worker:unhealthy"

def test_material_projection_ignores_unrelated_page_noise(tmp_path):
    from agentos_node.monitor_runtime import material_projection, evaluate
    a=material_projection("chatgpt-plus","<html><body><p>ChatGPT Plus $20 per month</p><p>footer A</p></body></html>")
    b=material_projection("chatgpt-plus","<html><body><p>ChatGPT Plus $20 per month</p><p>footer B</p></body></html>")
    assert a["material_sha256"]==b["material_sha256"]
    sp={"schema":"agentos.monitor/v1","monitor":{"id":"plan2"},"goal":{"description":"plan"},
      "schedule":{"every":"7d"},"execution":{"capability":"web.official.snapshot"},"payload":{"source":"chatgpt-plus"},
      "notification_policy":{"severity":"medium","cooldown":"7d"}}
    s=MonitorStore(tmp_path/"m.sqlite3"); s.register(sp)
    s.db.execute("update monitors set baseline_json=?,last_checked=? where monitor_id='plan2'",
      (json.dumps({"material_sha256":a["material_sha256"]}),"2026-10-06T00:00:00Z")); s.db.commit()
    row=s.inspect("plan2")
    d=DispatchResult(True,{"source":"chatgpt-plus","material_sha256":b["material_sha256"]},{"capability":"web.official.snapshot"})
    trig,*_=evaluate(sp,row,d)
    assert trig is False

def test_material_projection_detects_relevant_change(tmp_path):
    from agentos_node.monitor_runtime import material_projection
    a=material_projection("chatgpt-plus","<p>ChatGPT Plus $20 per month</p>")
    b=material_projection("chatgpt-plus","<p>ChatGPT Plus $25 per month</p>")
    assert a["material_sha256"]!=b["material_sha256"]
