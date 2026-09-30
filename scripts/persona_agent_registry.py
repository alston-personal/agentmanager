#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PERSONAS=ROOT/"personas"

def parse_simple_yaml(path:Path):
    # Manifest reader intentionally supports only the small stable subset needed
    # by AgentOS discovery. Runtime authority remains the manifest itself.
    text=path.read_text(encoding="utf-8")
    out={"path":str(path.relative_to(ROOT)),"capabilities":[]}
    for raw in text.splitlines():
        line=raw.strip()
        if line.startswith("agent_id:"):
            out["agent_id"]=line.split(":",1)[1].strip()
        elif line.startswith("display_name:"):
            out["display_name"]=line.split(":",1)[1].strip()
        elif line.startswith("status:") and "status" not in out:
            out["status"]=line.split(":",1)[1].strip()
        elif line.startswith("- id:"):
            out["capabilities"].append(line.split(":",1)[1].strip())
    return out

def agents():
    rows=[]
    if not PERSONAS.exists():
        return rows
    for p in sorted(PERSONAS.glob("*/agent.yaml")):
        row=parse_simple_yaml(p)
        if row.get("agent_id"):
            rows.append(row)
    return rows

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--json",action="store_true")
    ap.add_argument("--capability")
    args=ap.parse_args()
    rows=agents()
    if args.capability:
        rows=[r for r in rows if args.capability in r.get("capabilities",[])]
    if args.json:
        print(json.dumps({"schema":"agentos.persona-agent-registry/v1","agents":rows},ensure_ascii=False,indent=2))
    else:
        for r in rows:
            print(f"{r.get('agent_id')}\t{r.get('status','unknown')}\t{r.get('display_name','')}\t{','.join(r.get('capabilities',[]))}")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
