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

# A transport hint is NOT an install instruction.  This pure contract deliberately
# performs no network calls or code execution; ONE-owned bootstrap must validate
# identity, catalog signatures, policy, and provenance independently.
from urllib.parse import urlsplit

ADAPTER_HINT = "agentos.adapter-invalidation-hint/v1"
ADAPTER_PLAN = "agentos.adapter-reconciliation-plan/v1"
ADAPTER_ID = re.compile(r"^[a-z][a-z0-9._-]{0,95}$")
ADAPTER_VERSION = re.compile(r"^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _adapter_version(value):
    if not isinstance(value, str) or not ADAPTER_VERSION.fullmatch(value):
        raise ValueError("invalid_adapter_version")
    return tuple(int(part) for part in value.split("."))


def validate_adapter_hint(hint, *, trusted_one_origin):
    """Validate untrusted locator shape, never grant download/install authority."""
    if not isinstance(hint, dict) or set(hint) != {
        "schema", "notice_epoch", "adapter_id", "adapter_url",
        "adapter_version", "adapter_sha256",
    } or hint.get("schema") != ADAPTER_HINT:
        raise ValueError("invalid_adapter_hint")
    if type(hint["notice_epoch"]) is not int or hint["notice_epoch"] < 1:
        raise ValueError("invalid_notice_epoch")
    if not isinstance(hint["adapter_id"], str) or not ADAPTER_ID.fullmatch(hint["adapter_id"]):
        raise ValueError("invalid_adapter_id")
    _adapter_version(hint["adapter_version"])
    if not isinstance(hint["adapter_sha256"], str) or not DIGEST.fullmatch(hint["adapter_sha256"]):
        raise ValueError("invalid_adapter_digest")
    origin = urlsplit(trusted_one_origin)
    target = urlsplit(str(hint["adapter_url"]))
    if (origin.scheme != "https" or not origin.hostname or origin.username or origin.password
            or origin.query or origin.fragment or origin.path not in ("", "/")):
        raise ValueError("invalid_trusted_one_origin")
    if (target.scheme != "https" or not target.hostname or target.username or target.password
            or target.query or target.fragment or not target.path.startswith("/")):
        raise ValueError("invalid_adapter_url")
    if (target.scheme, target.netloc) != (origin.scheme, origin.netloc):
        raise ValueError("untrusted_adapter_origin")
    if "%2f" in target.path.lower() or "/../" in target.path or "/./" in target.path:
        raise ValueError("unsafe_adapter_path")
    return dict(hint)


def plan_adapter_reconciliation(*, hint, trusted_one_origin, authoritative_manifest,
                                installed_version=None, installed_sha256=None):
    """Return a bounded plan; caller must fetch/attest ONE manifest independently.

    This method cannot approve install, download, or launch an adapter.
    """
    hint = validate_adapter_hint(hint, trusted_one_origin=trusted_one_origin)
    if not isinstance(authoritative_manifest, dict):
        raise ValueError("missing_one_adapter_manifest")
    required = {"adapter_id", "adapter_version", "adapter_url", "adapter_sha256", "approved"}
    if set(authoritative_manifest) != required or authoritative_manifest["approved"] is not True:
        raise ValueError("unapproved_one_adapter_manifest")
    for key in ("adapter_id", "adapter_version", "adapter_url", "adapter_sha256"):
        if authoritative_manifest[key] != hint[key]:
            raise ValueError("adapter_manifest_mismatch")
    newest = _adapter_version(hint["adapter_version"])
    current = _adapter_version(installed_version) if installed_version is not None else None
    if installed_sha256 is not None and (
            not isinstance(installed_sha256, str) or not DIGEST.fullmatch(installed_sha256)):
        raise ValueError("invalid_installed_digest")
    if current is not None and current > newest:
        action = "KEEP_NEWER_LOCAL_AND_VERIFY_COMPATIBILITY"
    elif current == newest and installed_sha256 == hint["adapter_sha256"]:
        action = "HANDLE_EVENT"
    else:
        action = "REQUEST_GOVERNED_ADAPTER_UPDATE"
    return {
        "schema": ADAPTER_PLAN, "adapter_id": hint["adapter_id"],
        "target_adapter_version": hint["adapter_version"],
        "notice_epoch": hint["notice_epoch"],
        "action": action, "installation_authorized": False,
        "handler_execution_authorized": False,
    }


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
