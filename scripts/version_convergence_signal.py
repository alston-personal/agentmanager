#!/usr/bin/env python3
"""Pure source-generation and fail-closed acknowledgement contract for ONE.
No delivery, Git mutation, deployment, or authority is performed here.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

EVENT="agentos.version-convergence-event/v1"
ACK="agentos.version-convergence-ack/v1"
SHA=re.compile(r"^[0-9a-f]{40}$")
ID=re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
STATES={"NOTIFIED","SOURCE_CONVERGED","RUNTIME_DEPLOYED","TASK_RESUMED","BLOCKED"}

def stamp(value):
    if not isinstance(value,str): raise ValueError("invalid_timestamp")
    try: t=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError as e: raise ValueError("invalid_timestamp") from e
    if not t.tzinfo: raise ValueError("timezone_required")
    return t.astimezone(timezone.utc).isoformat().replace("+00:00","Z")

def sha(value):
    if not isinstance(value,str) or not SHA.fullmatch(value): raise ValueError("invalid_sha")
    return value

def paths_valid(paths):
    if not isinstance(paths,list) or not 0<len(paths)<=1000: raise ValueError("invalid_paths")
    for p in paths:
        if not isinstance(p,str) or not 0<len(p)<=256 or p.startswith("/") or "\\" in p:
            raise ValueError("invalid_path")
        if any(x in ("", ".", "..") for x in p.split("/")) or any(ord(c)<32 for c in p):
            raise ValueError("invalid_path")
    return sorted(set(paths))

def affected_domains(paths):
    domains=set()
    for p in paths_valid(paths):
        if p.startswith(("agent_core/","runtime_core/","agentos_node/")): d="core"
        elif p.startswith((".github/workflows/","scripts/deploy_","scripts/install_")): d="release"
        elif p.startswith(("scripts/","tests/")): d="application"
        elif p.startswith(("docs/","governance/",".agentos/",".agent/")): d="governance"
        else: d="unclassified"
        domains.add(d)
    return sorted(domains)

def make_event(*,repository,main_sha,previous_sha,changed_paths,published_at,pr_number=None):
    if repository!="alston-personal/agentmanager": raise ValueError("repository_not_authorized")
    sha(main_sha); sha(previous_sha)
    if main_sha==previous_sha: raise ValueError("generation_not_advanced")
    if pr_number is not None and (type(pr_number)!=int or pr_number<1): raise ValueError("invalid_pr")
    paths=paths_valid(changed_paths)
    eid=hashlib.sha256((repository+"|"+main_sha).encode()).hexdigest()[:24]
    return {"schema":EVENT,"event_id":"main-"+eid,"repository":repository,
            "target_main_sha":main_sha,"previous_main_sha":previous_sha,
            "merged_pr":pr_number,"changed_paths":paths,"affected_domains":affected_domains(paths),
            "published_at":stamp(published_at),"authority":"protected_main_readback",
            "effect":"notify_only","execution_authorized":False}

def validate_ack(event,ack):
    """Validate shape, NOT issuer identity or actual Git/runtime provenance.
    ONE must independently attest both before accepting the claim.
    """
    if not isinstance(event,dict) or event.get("schema")!=EVENT or event.get("effect")!="notify_only":
        raise ValueError("invalid_event")
    if not isinstance(ack,dict) or ack.get("schema")!=ACK: raise ValueError("invalid_ack")
    if ack.get("event_id")!=event.get("event_id") or ack.get("target_main_sha")!=event.get("target_main_sha"):
        raise ValueError("event_mismatch")
    for key in ("executor_id","task_id"):
        if not isinstance(ack.get(key),str) or not ID.fullmatch(ack[key]):
            raise ValueError("invalid_identity")
    state=ack.get("state")
    if state not in STATES: raise ValueError("invalid_state")
    observed=ack.get("observed_base_sha")
    deployed=ack.get("deployed_source_sha")
    if observed is not None: sha(observed)
    if deployed is not None: sha(deployed)
    stamp(ack.get("acknowledged_at"))
    if ack.get("dirty_worktree_preserved") is not True: raise ValueError("unsafe_worktree")
    if ack.get("write_authorized") is not False: raise ValueError("ack_cannot_grant_write")
    if state in ("SOURCE_CONVERGED","RUNTIME_DEPLOYED","TASK_RESUMED") and observed!=event["target_main_sha"]:
        raise ValueError("source_not_converged")
    if state=="RUNTIME_DEPLOYED" and deployed!=event["target_main_sha"]:
        raise ValueError("runtime_not_attested")
    if state=="BLOCKED" and not isinstance(ack.get("reason"),str):
        raise ValueError("missing_block_reason")
    return dict(ack)

def main():
    parser=argparse.ArgumentParser()
    for name in ("main-sha","previous-sha","paths-file","published-at","output"):
        parser.add_argument("--"+name,required=True)
    parser.add_argument("--pr-number",type=int)
    args=parser.parse_args()
    event=make_event(repository="alston-personal/agentmanager",main_sha=args.main_sha,
                     previous_sha=args.previous_sha,
                     changed_paths=Path(args.paths_file).read_text(encoding="utf-8").splitlines(),
                     published_at=args.published_at,pr_number=args.pr_number)
    Path(args.output).write_text(json.dumps(event,sort_keys=True,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"event_id":event["event_id"],"state":"CREATED_NOT_DELIVERED",
                      "target_main_sha":event["target_main_sha"],
                      "affected_domains":event["affected_domains"]},sort_keys=True))

if __name__=="__main__": main()
