#!/usr/bin/env python3
"""Oracle Monthly Report Coordinator (capability://governance.report.monthly).

Architecture:
1. Node Registry: Maintains registered DQA collector nodes (default: dqa03backup, dqa03restore, vopc5750).
2. Strict Public/Private Isolation: Whitelists ONLY DQA official projects
   (system, redmine_5, testrail, samba, 伺服器維運) and hard-blocks personal/research
   keywords (agentos, mio, wow, zeus-writer, youtube, tarot, etc.).
3. Dispatch-and-Await: Broadcasts bounded read-only slice collection tasks to online
   nodes via Realm Fabric (`agent_core.realm_cli`), waits with timeout/fault-tolerance,
   and aggregates `agentos.monthly-report-slice/v1` payloads.
4. Human Review Gate: Persists a review draft JSON + Confluence Markdown preview.
   Publishing to Confluence on vopc5750 is PHYSICALLY BLOCKED until explicit human approval
   (with optional item deletions/edits) is recorded in the review state.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SKILL_SCRIPTS = Path(__file__).resolve().parent.parent / ".agent" / "skills" / "monthly_report" / "scripts"
if str(SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SKILL_SCRIPTS))

from date_calculator import get_report_metadata  # noqa: E402

CAPABILITY_ID = "capability://governance.report.monthly"
DEFAULT_REGISTERED_NODES = ("dqa03backup", "dqa03restore", "vopc5750")

# 公私界限絕對隔離：白名單與硬性黑名單
ALLOWED_DQA_PROJECTS = frozenset({"system", "redmine_5", "testrail", "samba", "伺服器維運"})
FORBIDDEN_PERSONAL_KEYWORDS = (
    "agentos",
    "agentmanager",
    "mio",
    "sunlake",
    "wow",
    "world of warcraft",
    "zeus-writer",
    "天道敕令",
    "奇幻編年史",
    "youtube-ai",
    "tarot",
    "duel-plugin",
    "ip-genome",
    "dressup",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def is_dqa_work_item_allowed(project: str, text: str) -> tuple[bool, str]:
    """Fail-closed public/private isolation filter."""
    proj_norm = str(project or "").strip().lower()
    combined = f"{proj_norm} {str(text or '').lower()}"
    for kw in FORBIDDEN_PERSONAL_KEYWORDS:
        if kw in combined:
            return False, f"forbidden_personal_keyword:{kw}"
    if proj_norm and proj_norm not in ALLOWED_DQA_PROJECTS:
        return False, f"project_not_in_dqa_whitelist:{proj_norm}"
    return True, "ok"


def filter_and_merge_slices(
    slices: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Filter node slices through strict DQA whitelist and return (accepted, rejected)."""
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for sl in slices:
        node_id = str(sl.get("node_id") or "unknown")
        for item in sl.get("items") or []:
            project = str(item.get("project") or "system")
            title = str(item.get("title") or "").strip()
            status = str(item.get("status") or "proceeding").strip().lower()
            subitems = [str(s).strip() for s in (item.get("subitems") or []) if str(s).strip()]
            full_text = " ".join([title, *subitems])

            ok, reason = is_dqa_work_item_allowed(project, full_text)
            entry = {
                "item_id": f"{node_id}:{project}:{len(accepted) + len(rejected) + 1}",
                "node_id": node_id,
                "project": project,
                "title": title,
                "status": "completed" if status == "completed" else "proceeding",
                "subitems": subitems,
                "recent_week": bool(item.get("recent_week", False)),
            }
            if ok and title:
                accepted.append(entry)
            else:
                entry["rejected_reason"] = reason if not ok else "empty_title"
                rejected.append(entry)

    return accepted, rejected


def render_confluence_markdown(
    metadata: dict[str, Any],
    items: list[dict[str, Any]],
) -> str:
    """Render Confluence-ready Weekly/Monthly Report Markdown."""
    lines = [
        f"# {metadata['page_title']}",
        "",
        "| Field | Value |",
        "| :--- | :--- |",
        f"| **Date** | {metadata['report_date_table']} |",
        f"| **Reporter** | @{metadata['reporter']} |",
        "",
        "## 本週工作重點",
    ]
    highlights = [it for it in items if it.get("recent_week")]
    if not highlights:
        highlights = items[:5]
    if not highlights:
        lines.append("- (尚無本週重點項目)")
    else:
        for it in highlights:
            lines.append(f"- [{it['project']}] {it['title']} ({it['status']})")

    lines.append("")
    lines.append("## 進度與狀態記錄")
    if not items:
        lines.append("- (尚無已核准之 DQA 工作項目)")
    else:
        for it in items:
            lines.append(f"- **[{it['project']}] {it['title']}** (`{it['node_id']}`)")
            lines.append(f"  - {it['status']}")
            for sub in it.get("subitems") or []:
                lines.append(f"  - {sub}")
    return "\n".join(lines) + "\n"


def build_review_package(
    *,
    year: int,
    month: int,
    slices: list[dict[str, Any]],
    override_date: str | None = None,
    registered_nodes: tuple[str, ...] = DEFAULT_REGISTERED_NODES,
) -> dict[str, Any]:
    """Create a pending Human Review Gate package (publish_authorized is ALWAYS False initially)."""
    meta = get_report_metadata(year, month, override_date=override_date)
    accepted, rejected = filter_and_merge_slices(slices)
    markdown = render_confluence_markdown(meta, accepted)
    return {
        "schema": "agentos.monthly-report-review/v1",
        "capability": CAPABILITY_ID,
        "created_at": _utc_now_iso(),
        "registered_nodes": list(registered_nodes),
        "metadata": meta,
        "accepted_items": accepted,
        "rejected_items": rejected,
        "markdown_preview": markdown,
        "review_gate": {
            "status": "AWAITING_HUMAN_REVIEW",
            "publish_authorized": False,
            "target_browser_node": "vopc5750",
        },
    }


def apply_human_review(
    package: dict[str, Any],
    *,
    remove_item_ids: set[str] | None = None,
    approve_publish: bool = False,
) -> dict[str, Any]:
    """Apply user deletions/edits and optionally unlock the Human Review Gate."""
    remove_ids = remove_item_ids or set()
    kept = [it for it in package.get("accepted_items", []) if it.get("item_id") not in remove_ids]
    updated = dict(package)
    updated["accepted_items"] = kept
    updated["markdown_preview"] = render_confluence_markdown(package["metadata"], kept)
    updated["review_gate"] = {
        "status": "APPROVED_FOR_PUBLISH" if approve_publish else "AWAITING_HUMAN_REVIEW",
        "publish_authorized": bool(approve_publish),
        "target_browser_node": "vopc5750",
        "reviewed_at": _utc_now_iso(),
    }
    return updated


def assert_publish_allowed(package: dict[str, Any]) -> None:
    """Fail-closed guard: block Confluence browser publish unless Human Review Gate is approved."""
    gate = package.get("review_gate") or {}
    if not gate.get("publish_authorized") or gate.get("status") != "APPROVED_FOR_PUBLISH":
        raise PermissionError(
            "HUMAN_REVIEW_GATE_BLOCKED: 月報尚未獲得使用者明確審核確認，嚴禁執行 Confluence 發布。"
        )
    if gate.get("target_browser_node") != "vopc5750":
        raise PermissionError("BROWSER_BOUNDARY_VIOLATION: Confluence GUI 操作僅允許在 vopc5750 執行。")
