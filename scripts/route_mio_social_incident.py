#!/usr/bin/env python3
from __future__ import annotations
import json, os, subprocess

run_id=os.environ["GITHUB_RUN_ID"]
attempt=int(os.environ.get("GITHUB_RUN_ATTEMPT") or "1")
workflow=os.environ.get("GITHUB_WORKFLOW") or "Mio social workflow"
sha=os.environ.get("GITHUB_SHA") or ""
repo=os.environ["GITHUB_REPOSITORY"]
title=f"[Mio Incident] {workflow} failed (run {run_id}, attempt {attempt})"
body=(
    "Mio autonomous social operation failed and was routed automatically.\n\n"
    f"- workflow: {workflow}\n- run_id: {run_id}\n- attempt: {attempt}\n- source_commit: {sha}\n\n"
    "Acceptance rule: keep open until a later PASS receipt is observed.\n"
)
cp=subprocess.run(
    ["gh","issue","create","--repo",repo,"--title",title,"--body",body],
    text=True,capture_output=True,check=True,
)
url=cp.stdout.strip()
issue_no=url.rstrip("/").split("/")[-1]
print("mio_incident_issue="+issue_no)
if attempt == 1:
    subprocess.run(
        ["gh","workflow","run","mio-social-incident-repair.yml","--repo",repo,
         "--ref","core/integration",
         "-f","source_run_id="+run_id,
         "-f","source_workflow="+workflow[:80],
         "-f","incident_issue="+issue_no],
        check=True,
    )
    print("mio_incident_repair_dispatch=PASS")
else:
    print("mio_incident_repair_dispatch=ESCALATED_NO_RETRY")
