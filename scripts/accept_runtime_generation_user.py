#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os, re, subprocess
from pathlib import Path

SHA=re.compile(r"^[0-9a-f]{40}$")
DATA=Path(os.environ.get("AGENT_DATA_ROOT") or "/home/ubuntu/agent-data")

def unit_commit(unit,key):
    p=subprocess.run(["systemctl","--user","show",unit,"-p","Environment","--value"],capture_output=True,text=True,check=False)
    m=re.search(r"(?:^|\\s)"+re.escape(key)+r"=([0-9a-f]{40})(?:\\s|$)",p.stdout or "")
    return m.group(1) if m else ""

def json_commit(path):
    try: v=str(json.loads(path.read_text()).get("source_commit") or "")
    except Exception: return ""
    return v if SHA.fullmatch(v) else ""

def core_commit():
    p=DATA/"runtime/core/current"
    try:
        target=p.resolve(strict=True)
        v=target.name
        return v if SHA.fullmatch(v) else ""
    except Exception: return ""

def action_commit():
    return json_commit(DATA/"runtime/action-relay/capabilities.json") or unit_commit("agentos-action-relay.service","AGENTOS_ACTION_RUNTIME_SOURCE_COMMIT")

def realm_commit():
    return json_commit(DATA/"runtime/realm-fabric/provenance.json") or unit_commit("agentos-realm-fabric.service","AGENTOS_REALM_RUNTIME_SOURCE_COMMIT")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--expected",required=True)
    a=ap.parse_args()
    if not SHA.fullmatch(a.expected): raise SystemExit("expected must be exact 40-hex SHA")
    observed={"core":core_commit(),"action":action_commit(),"realm":realm_commit()}
    ok=all(v==a.expected for v in observed.values())
    print(json.dumps({"schema":"agentos.runtime-generation-acceptance/v1","expected_source_commit":a.expected,"observed":observed,"ok":ok},sort_keys=True))
    for k,v in observed.items(): print(f"runtime_generation_{k}_source_commit={v or 'UNKNOWN'}")
    print("runtime_generation_acceptance="+("PASS" if ok else "FAIL"))
    raise SystemExit(0 if ok else 10)

if __name__=="__main__": main()
