#!/usr/bin/env python3
"""AgentOS Incident Queue & Triage Protocol (agentos.incident-queue/v1)

Implements two-phase anomaly management:
Phase 1: Detection -> Incident Queue (Sentinel detects anomalies and enqueues)
Phase 2: Triage & Verification -> Dispatch (Spec Steward & Claw verify drift vs false positives)
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA_ROOT = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
INCIDENT_ROOT = DATA_ROOT / "runtime" / "incident-queue"
PENDING_DIR = INCIDENT_ROOT / "pending"
TRIAGED_DIR = INCIDENT_ROOT / "triaged"
SUPPRESSED_DIR = INCIDENT_ROOT / "suppressed"

VERDICTS = {
    "CONFIRMED_DEFECT",      # True bug -> dispatch to The Paw for fix
    "SPEC_DRIFT",           # Behavior diverged from spec -> dispatch to Spec Steward / Weaver
    "FALSE_POSITIVE",       # False alarm -> add suppression rule and close
    "TRANSIENT_FAULT",      # Temporary / self-healing -> retry or wait
    "AWAITING_HUMAN_APPROVAL" # High-risk or policy change -> notify human
}

def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

def ensure_dirs() -> None:
    for d in (PENDING_DIR, TRIAGED_DIR, SUPPRESSED_DIR):
        d.mkdir(parents=True, exist_ok=True)

def enqueue_incident(
    *,
    detector: str,
    target: str,
    incident_type: str,
    evidence: dict[str, Any],
    severity: str = "medium",
    summary: str = "",
) -> dict[str, Any]:
    """Phase 1: Detector discovers an anomaly and enqueues it without taking destructive action."""
    ensure_dirs()
    incident_id = f"inc_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    record = {
        "schema": "agentos.incident/v1",
        "incident_id": incident_id,
        "detector": detector,
        "target": target,
        "incident_type": incident_type,
        "severity": severity,
        "summary": summary or f"{detector} reported {incident_type} on {target}",
        "evidence": evidence,
        "detected_at": _now_iso(),
        "status": "pending_triage",
        "triage": None,
    }
    path = PENDING_DIR / f"{incident_id}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record

def list_pending_incidents() -> list[dict[str, Any]]:
    ensure_dirs()
    results = []
    for f in sorted(PENDING_DIR.glob("*.json")):
        try:
            results.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return results

def triage_incident(
    incident_id: str,
    *,
    reviewer: str,
    verdict: str,
    analysis: str,
    dispatched_to: str | None = None,
    dispatched_task: str | None = None,
) -> dict[str, Any]:
    """Phase 2: Spec Steward or The Claw audits the incident, separating true bugs from false positives."""
    ensure_dirs()
    pending_file = PENDING_DIR / f"{incident_id}.json"
    if not pending_file.exists():
        raise FileNotFoundError(f"Incident {incident_id} not found in pending queue")

    record = json.loads(pending_file.read_text(encoding="utf-8"))
    if verdict not in VERDICTS:
        raise ValueError(f"Invalid verdict '{verdict}'. Must be one of {VERDICTS}")

    triage_info = {
        "triaged_at": _now_iso(),
        "reviewer": reviewer,
        "verdict": verdict,
        "analysis": analysis,
        "dispatched_to": dispatched_to,
        "dispatched_task": dispatched_task,
    }
    record["triage"] = triage_info
    record["status"] = "triaged" if verdict != "FALSE_POSITIVE" else "suppressed"

    dest_dir = SUPPRESSED_DIR if verdict == "FALSE_POSITIVE" else TRIAGED_DIR
    target_file = dest_dir / f"{incident_id}.json"
    target_file.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    pending_file.unlink(missing_ok=True)
    return record

