#!/usr/bin/env python3
"""Deterministic offline lookup of verified historical AgentOS capabilities."""
import argparse
import json
from pathlib import Path

MANIFEST_DIR=Path(__file__).resolve().parents[1]/"capabilities/recovery"

def lookup(capability,root=MANIFEST_DIR):
    entries=[]
    for path in sorted(root.glob("*.json")):
        manifest=json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("schema")!="agentos.capability-recovery-manifest/v1":
            continue
        if manifest.get("capability_id")==capability:
            entries.append({"manifest":str(path),"capability":manifest})
    return entries

def main():
    p=argparse.ArgumentParser()
    p.add_argument("capability",help="Capability ID, e.g. social.threads.publish.image")
    args=p.parse_args()
    hits=lookup(args.capability)
    print(json.dumps({"found":len(hits),"matches":hits},ensure_ascii=False,indent=2))
    return 0 if hits else 2

if __name__=="__main__":
    raise SystemExit(main())
