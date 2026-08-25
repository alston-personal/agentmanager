#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_core.governance_directory import (  # noqa: E402
    REGISTRY_PATH,
    get,
    list_entities,
    load_directory,
    mark_verified,
    resolve,
    seed_core,
)

DATA_ROOT = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
PORT_REGISTRY = DATA_ROOT / "config" / "port_registry.json"
SERVICES_FILE = ROOT / ".agent" / "SERVICES.md"
WATCHDOG_FILE = ROOT / "scripts" / "os_watchdog.py"
ROLE_ROOT = ROOT / ".agent" / "roles"
REPORT_ROOT = DATA_ROOT / "journals" / "governance_directory"


def _age_days(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except Exception:
        return None


def audit() -> dict:
    seed_core()
    directory = load_directory()
    findings: list[dict] = []

    # 1. Exclusive capability duplication.
    owners: dict[str, list[str]] = {}
    for entity in directory["entities"].values():
        if entity.get("state") in {"retired", "superseded"}:
            continue
        if entity.get("authority", {}).get("exclusive"):
            for cap in entity.get("owns", []):
                owners.setdefault(cap, []).append(entity["id"])
    for cap, ids in owners.items():
        if len(ids) > 1:
            findings.append({"severity":"error","code":"exclusive_owner_conflict","subject":cap,"detail":ids})

    # 2. Implementation paths should exist.
    for entity in directory["entities"].values():
        impl = entity.get("implementation", {})
        for key in ("path", "definition", "registry"):
            rel = impl.get(key)
            if not rel or str(rel).startswith("/home/"):
                continue
            path = ROOT / rel
            if not path.exists():
                findings.append({"severity":"error","code":"implementation_missing","subject":entity["id"],"detail":str(rel)})

    # 3. Role instance state freshness. Definitions are durable; instances with Current Pulse are not.
    for path in sorted((ROLE_ROOT / "instances").glob("*.md")) if (ROLE_ROOT / "instances").exists() else []:
        text = path.read_text(encoding="utf-8", errors="replace")
        if "Current Pulse" in text or "當前脈搏" in text:
            age = max(0, (datetime.now(timezone.utc) - datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)).days)
            if age >= 30:
                findings.append({"severity":"warning","code":"stale_role_instance_pulse","subject":str(path.relative_to(ROOT)),"detail":f"{age} days old"})

    # 4. Service declaration ↔ watchdog implementation drift.
    declared: set[str] = set()
    if SERVICES_FILE.exists():
        text = SERVICES_FILE.read_text(encoding="utf-8", errors="replace")
        declared.update(re.findall(r"`([^`]+\.service)`", text))
    monitored: set[str] = set()
    if WATCHDOG_FILE.exists():
        text = WATCHDOG_FILE.read_text(encoding="utf-8", errors="replace")
        # Narrow extraction of systemd service literals from implementation.
        monitored.update(re.findall(r'["\']([a-zA-Z0-9_.@-]+\.service)["\']', text))
    if declared or monitored:
        for svc in sorted(declared - monitored):
            findings.append({"severity":"warning","code":"declared_service_not_monitored","subject":svc,"detail":"SERVICES.md declares it but watchdog source does not reference it"})
        for svc in sorted(monitored - declared):
            findings.append({"severity":"warning","code":"monitored_service_not_declared","subject":svc,"detail":"watchdog source references it but SERVICES.md does not declare it"})

    # 5. Port registry is a governed resource and should not have duplicate project claims.
    if PORT_REGISTRY.exists():
        try:
            ports = json.loads(PORT_REGISTRY.read_text(encoding="utf-8"))
            by_project: dict[str, list[str]] = {}
            for port, info in ports.items():
                project = str(info.get("project", "unknown"))
                by_project.setdefault(project, []).append(str(port))
            for project, values in by_project.items():
                if len(values) > 1:
                    findings.append({"severity":"warning","code":"project_multiple_port_claims","subject":project,"detail":sorted(values)})
        except Exception as exc:
            findings.append({"severity":"error","code":"port_registry_invalid","subject":str(PORT_REGISTRY),"detail":str(exc)})

    # 6. Verification freshness for active runtime entities.
    for entity in directory["entities"].values():
        if entity.get("kind") not in {"manager", "service", "resource", "node"}:
            continue
        if entity.get("state") in {"retired", "superseded"}:
            continue
        age = _age_days(entity.get("last_verified_at"))
        if age is None:
            findings.append({"severity":"warning","code":"never_verified","subject":entity["id"],"detail":"no last_verified_at"})
        elif age >= 14:
            findings.append({"severity":"warning","code":"verification_stale","subject":entity["id"],"detail":f"{age} days old"})

    return {
        "schema_version": "0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "registry": str(REGISTRY_PATH),
        "entities": len(directory["entities"]),
        "findings": findings,
        "summary": {
            "errors": sum(1 for f in findings if f["severity"] == "error"),
            "warnings": sum(1 for f in findings if f["severity"] == "warning"),
        },
    }


def render(report: dict) -> str:
    s = report["summary"]
    lines = [
        "# AgentOS Governance Directory Audit",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Entities: **{report['entities']}**",
        f"- Errors: **{s['errors']}**",
        f"- Warnings: **{s['warnings']}**",
        "",
        "| Severity | Code | Subject | Detail |",
        "|---|---|---|---|",
    ]
    if not report["findings"]:
        lines.append("| ok | aligned | — | No drift detected |")
    for f in report["findings"]:
        detail = json.dumps(f["detail"], ensure_ascii=False) if not isinstance(f["detail"], str) else f["detail"]
        lines.append(f"| {f['severity']} | `{f['code']}` | `{f['subject']}` | {detail} |")
    lines += [
        "",
        "## Operating Rule",
        "Before implementing a new cross-project/system capability: resolve it in the Governance Directory. If an active owner exists, reuse or extend that owner. Discovery is allowed only when resolution fails; newly discovered reusable capabilities must be registered.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description="AgentOS Governance Directory")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed")
    lp = sub.add_parser("list"); lp.add_argument("--kind")
    gp = sub.add_parser("get"); gp.add_argument("id")
    rp = sub.add_parser("resolve"); rp.add_argument("capability")
    vp = sub.add_parser("verify"); vp.add_argument("id"); vp.add_argument("--state", default="verified")
    ap = sub.add_parser("audit"); ap.add_argument("--json", action="store_true"); ap.add_argument("--write", action="store_true")
    args = p.parse_args()

    if args.cmd == "seed":
        seed_core(); print(REGISTRY_PATH); return 0
    if args.cmd == "list":
        seed_core(); print(json.dumps(list_entities(args.kind), ensure_ascii=False, indent=2)); return 0
    if args.cmd == "get":
        seed_core(); obj = get(args.id); print(json.dumps(obj, ensure_ascii=False, indent=2)); return 0 if obj else 1
    if args.cmd == "resolve":
        seed_core(); print(json.dumps(resolve(args.capability), ensure_ascii=False, indent=2)); return 0
    if args.cmd == "verify":
        seed_core(); print(json.dumps(mark_verified(args.id, args.state), ensure_ascii=False, indent=2)); return 0
    if args.cmd == "audit":
        report = audit()
        output = json.dumps(report, ensure_ascii=False, indent=2) if args.json else render(report)
        print(output)
        if args.write:
            REPORT_ROOT.mkdir(parents=True, exist_ok=True)
            path = REPORT_ROOT / f"audit_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.md"
            path.write_text(render(report), encoding="utf-8")
            print(f"Saved to: {path}")
        return 2 if report["summary"]["errors"] else 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
