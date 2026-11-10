#!/usr/bin/env python3
"""Incident Sentinel & Triage CLI (agentos.incident-queue/v1)

Usage:
  python3 scripts/incident_sentinel.py --scan    # Run detection patrol and enqueue anomalies
  python3 scripts/incident_sentinel.py --list    # List pending incidents in the triage queue
  python3 scripts/incident_sentinel.py --triage <incident_id> --verdict CONFIRMED_DEFECT --reviewer the_claw ...
"""
from __future__ import annotations

import argparse
import json
import urllib.request
import urllib.error
import ssl
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_core.incident_queue import (
    enqueue_incident,
    list_pending_incidents,
    triage_incident,
    VERDICTS,
)

CRITICAL_ROUTES = [
    ("https://studio.milkcat.org/", "Studio Portal"),
    ("https://studio.milkcat.org/role-island/", "3D Role Island"),
    ("https://studio.milkcat.org/personas/mio/", "Mio Activity / Cozy Room"),
    ("https://studio.milkcat.org/mio-room/", "Mio Room Redirect Entry"),
    ("https://studio.milkcat.org/dashboard/", "Flight Deck Dashboard"),
    ("https://studio.milkcat.org/api/invoice-intake/v1/recent?limit=1", "Invoice Intake API"),
]

def scan_routes() -> int:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    detected = 0
    print("🔍 [Sentinel] Scanning critical routes...")
    for url, label in CRITICAL_ROUTES:
        req = urllib.request.Request(url, headers={"User-Agent": "AgentOS-Sentinel/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                code = resp.getcode()
                if code >= 400:
                    print(f"  ❌ {label} ({url}) returned HTTP {code}")
                    enqueue_incident(
                        detector="sentinel-route-probe",
                        target=url,
                        incident_type="ROUTE_ERROR",
                        severity="high",
                        summary=f"{label} returned HTTP {code}",
                        evidence={"url": url, "status_code": code},
                    )
                    detected += 1
                else:
                    print(f"  ✅ {label} ({url}) -> HTTP {code}")
        except urllib.error.HTTPError as e:
            print(f"  ❌ {label} ({url}) -> HTTP {e.code}")
            enqueue_incident(
                detector="sentinel-route-probe",
                target=url,
                incident_type="ROUTE_FALLBACK_OR_ERROR",
                severity="high",
                summary=f"{label} failed with HTTP {e.code}",
                evidence={"url": url, "status_code": e.code, "reason": str(e.reason)},
            )
            detected += 1
        except Exception as e:
            print(f"  ⚠️ {label} ({url}) connection failed: {e}")
            enqueue_incident(
                detector="sentinel-route-probe",
                target=url,
                incident_type="ROUTE_CONNECTION_TIMEOUT",
                severity="medium",
                summary=f"{label} connection error: {e}",
                evidence={"url": url, "error": str(e)},
            )
            detected += 1
    return detected

def scan_project_backlogs() -> int:
    print("🔍 [Sentinel] Scanning project backlogs for stalls...")
    data_root = Path("/home/ubuntu/agent-data/projects")
    detected = 0
    for status_file in data_root.glob("*/STATUS.md"):
        project_name = status_file.parent.name
        content = status_file.read_text(encoding="utf-8", errors="ignore")
        if "待復工" in content or "中斷" in content:
            print(f"  ⚠️ Project {project_name} flagged for stall: contains '待復工'")
            enqueue_incident(
                detector="sentinel-backlog-monitor",
                target=project_name,
                incident_type="PIPELINE_STALL",
                severity="medium",
                summary=f"Project {project_name} is marked as stalled/pending continuation",
                evidence={"status_file": str(status_file)},
            )
            detected += 1
    return detected

def main() -> int:
    parser = argparse.ArgumentParser(description="AgentOS Incident Sentinel & Triage")
    parser.add_argument("--scan", action="store_true", help="Run detection scan and enqueue incidents")
    parser.add_argument("--list", action="store_true", help="List all pending incidents in queue")
    parser.add_argument("--triage", type=str, metavar="INCIDENT_ID", help="Triage a specific incident")
    parser.add_argument("--reviewer", type=str, default="the_claw", help="Reviewer role (e.g. spec_steward, the_claw)")
    parser.add_argument("--verdict", type=str, choices=list(VERDICTS), help="Triage verdict")
    parser.add_argument("--analysis", type=str, default="", help="Reviewer analysis / reasoning")
    parser.add_argument("--dispatch-to", type=str, help="Role to dispatch task to (e.g. the_paw, weaver)")
    parser.add_argument("--dispatch-task", type=str, help="Specific task description to dispatch")

    args = parser.parse_args()

    if args.scan:
        r_count = scan_routes()
        b_count = scan_project_backlogs()
        print(f"\n📊 [Sentinel Scan Complete] Enqueued {r_count + b_count} incidents for triage.")
        return 0

    if args.list:
        items = list_pending_incidents()
        print(f"📋 [Pending Incident Queue] ({len(items)} items awaiting triage):")
        for item in items:
            print(f"  • [{item['incident_id']}] ({item['severity'].upper()}) {item['incident_type']} on {item['target']}")
            print(f"    Summary: {item['summary']}")
            print(f"    Detected by: {item['detector']} at {item['detected_at']}\n")
        return 0

    if args.triage:
        if not args.verdict:
            print("❌ --verdict is required when triaging")
            return 1
        res = triage_incident(
            args.triage,
            reviewer=args.reviewer,
            verdict=args.verdict,
            analysis=args.analysis or "Audited and verified by triage role.",
            dispatched_to=args.dispatch_to,
            dispatched_task=args.dispatch_task,
        )
        print(f"✅ Incident {args.triage} triaged successfully!")
        print(f"   Verdict: {res['triage']['verdict']} by {res['triage']['reviewer']}")
        if res['triage']['dispatched_to']:
            print(f"   Dispatched to: {res['triage']['dispatched_to']} -> {res['triage']['dispatched_task']}")
        return 0

    parser.print_help()
    return 0

if __name__ == "__main__":
    sys.exit(main())
