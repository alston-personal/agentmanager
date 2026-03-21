"""
actions/ecosystem_report.py
/ecosystem-report action — extracted from run_workflow.py.

Barrier-sync mechanism: scan all projects → check freshness → report.
Now reads from project.yaml when available (no regex fallback needed).
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from glob import glob
from pathlib import Path

from agent_core.context import RuntimeContext
from agent_core.registry import registry, ActionResult
from agent_core.config import CENTRAL_PROJECTS_DIR, JOURNALS_DIR, AGENT_DATA_ROOT
from agent_core.renderer import send_telegram
from agent_memory.event_store import emit as emit_event


@registry.register(
    "ecosystem-report",
    description="Full ecosystem health scan — all projects, system metrics, Telegram push",
    aliases=["eco"],
)
def handle_ecosystem_report(ctx: RuntimeContext) -> ActionResult:
    from agent_core.project_store import list_projects

    report_lines = ["# 🌐 Agent OS: Ecosystem Report", ""]
    tg_rows = []
    needs_update = []
    projects = list_projects()
    yaml_available = len(projects) > 0

    # -----------------------------------------------------------------------
    # System metrics
    # -----------------------------------------------------------------------
    uptime = os.popen("uptime -p").read().strip().replace("up ", "")
    mem_brief = _parse_memory()
    mem_full = os.popen("free -h | grep Mem").read().strip()

    report_lines += [
        "## 🖥️ System Health",
        f"- **Uptime**: {uptime}",
        f"- **Memory**: {mem_full}",
        "",
    ]

    # -----------------------------------------------------------------------
    # Project freshness check
    # -----------------------------------------------------------------------
    if yaml_available:
        # Structured path: read from project.yaml
        synced = [p for p in projects if p.health.freshness == "fresh"]
        stale = [p for p in projects if p.health.freshness != "fresh"]

        report_lines += [
            f"## 📦 Project Sync: `{len(synced)}/{len(projects)}`",
            "",
            "| Project | Sector | P | Phase | Health | Updated |",
            "| :--- | :---: | :---: | :---: | :---: | :--- |",
        ]

        HEALTH_ICON = {"fresh": "🟢", "stale": "🟡", "unknown": "⚪"}
        for p in sorted(projects, key=lambda x: -x.priority):
            icon = HEALTH_ICON.get(p.health.freshness, "⚪")
            updated_short = (p.updated_at or "")[:10]
            report_lines.append(
                f"| **{p.project_id}** | {p.sector} | {p.priority} "
                f"| {p.phase} | {icon} | {updated_short} |"
            )
            tg_rows.append({
                "name": p.project_id,
                "tag": "🟢 Fresh" if p.health.freshness == "fresh" else "🟡 Stale",
                "updated": updated_short,
            })

        needs_update = [p.project_id for p in stale]

    else:
        # Legacy fallback: regex
        report_lines.append("_(No project.yaml found — run `init_project_yaml.py` to upgrade)_")
        report_lines.append("")
        status_paths = sorted(glob(str(CENTRAL_PROJECTS_DIR / "*" / "STATUS.md")))
        synced_list, stale_list = _legacy_freshness_check(status_paths)
        needs_update = stale_list
        report_lines += _legacy_table(status_paths, stale_list)
        tg_rows = [{"name": s, "tag": "🟢 Verified", "updated": ""} for s in synced_list]
        tg_rows += [{"name": s, "tag": "🔴 Stale", "updated": ""} for s in stale_list]

    if needs_update:
        report_lines += [
            "",
            "### ⚠️ Needs Attention (Stale)",
            *[f"- `{p}` — run `/report` after next work session" for p in needs_update[:8]],
        ]

    # -----------------------------------------------------------------------
    # Save report to journals
    # -----------------------------------------------------------------------
    output = "\n".join(report_lines)
    _save_report(output)

    # -----------------------------------------------------------------------
    # Emit event
    # -----------------------------------------------------------------------
    emit_event(
        event_type="ecosystem_report",
        project_id="system",
        actor=ctx.agent_id,
        payload={"project_count": len(projects), "stale_count": len(needs_update)},
    )

    # -----------------------------------------------------------------------
    # Telegram push
    # -----------------------------------------------------------------------
    tg_msg = _format_tg(uptime, mem_brief, len(tg_rows) - len(needs_update), len(tg_rows), needs_update, tg_rows)
    send_telegram(tg_msg)

    return ActionResult.ok(output, data={"stale": needs_update})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_memory() -> str:
    try:
        res = os.popen("free -g | grep Mem").read().strip().split()
        if len(res) >= 3:
            return f"{res[2]}G / {res[1]}G"
    except Exception:
        pass
    return "N/A"


def _save_report(content: str) -> None:
    history_dir = JOURNALS_DIR / "ecosystem_reports"
    history_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    path = history_dir / f"report_{stamp}.md"
    path.write_text(content, encoding="utf-8")


def _legacy_freshness_check(status_paths: list) -> tuple[list, list]:
    synced, stale = [], []
    for sp in status_paths:
        name = Path(sp).parent.name
        status_mtime = os.path.getmtime(sp)
        actual_path = _extract_field(open(sp).read(), "Actual Code Path")
        is_fresh = True
        if actual_path and os.path.isdir(actual_path):
            cmd = f"find {actual_path} -maxdepth 3 -not -path '*/.*' -type f -printf '%T@\n' | sort -n | tail -1"
            res = os.popen(cmd).read().strip()
            if res and float(res) > status_mtime + 60:
                is_fresh = False
        (synced if is_fresh else stale).append(name)
    return synced, stale


def _legacy_table(status_paths, stale_list) -> list[str]:
    import re
    lines = [
        "| Project | Status | Updated | Activity |",
        "| :--- | :--- | :--- | :--- |",
    ]
    for sp in status_paths:
        name = Path(sp).parent.name
        content = open(sp).read()
        tag = "🔴 Stale" if name in stale_list else "🟢 Verified"
        lines.append(f"| **{name}** | {tag} | {_extract_field(content, 'Last Updated')} | |")
    return lines


def _extract_field(content: str, label: str) -> str:
    import re
    m = re.search(rf"\|\s*\*\*{re.escape(label)}\*\*\s*\|\s*([^|]+?)\s*\|", content)
    return m.group(1).strip() if m else ""


def _format_tg(uptime, memory, synced, total, needs_update, rows) -> str:
    from datetime import datetime
    ts = datetime.now().strftime("%H:%M")
    lines = [
        f"🌐 *Agent OS Pulse* ({ts})",
        "───────────────────",
        f"🖥️ Uptime: {uptime} | Mem: {memory}",
        f"📦 Sync: `{synced}/{total}` Fresh",
    ]
    if needs_update:
        lines.append(f"\n⚠️ *Stale ({len(needs_update)})*:")
        for p in needs_update[:5]:
            lines.append(f"  └─ 🔴 `{p}`")
    lines.append("\n📂 *Projects*:")
    for r in rows[:10]:
        icon = "🟢" if "Fresh" in r["tag"] or "Verified" in r["tag"] else "🟡"
        lines.append(f"  {icon} {r['name']} ({r['updated'] or 'N/A'})")
    return "\n".join(lines)
