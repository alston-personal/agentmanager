#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / ".agent" / "governance" / "oracle_identity_boundaries.json"
TEXT_SUFFIXES = {".py", ".sh", ".yml", ".yaml", ".json", ".service", ".timer", ".md", ".txt", ".ps1"}


def _tracked_files(root: Path) -> list[Path]:
    proc = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    result: list[Path] = []
    for raw in proc.stdout.split(b"\0"):
        if not raw:
            continue
        path = root / raw.decode("utf-8", "replace")
        if path.suffix.lower() in TEXT_SUFFIXES or path.name.endswith((".service", ".timer")):
            result.append(path)
    return result


def _under_review_root(rel: str, roots: list[str]) -> bool:
    return any(rel == root or rel.startswith(root.rstrip("/") + "/") for root in roots)


def _excluded(rel: str, patterns: list[str]) -> bool:
    from fnmatch import fnmatch
    return any(fnmatch(rel, pattern) for pattern in patterns)


def _classify(rel: str, text: str, policy: dict[str, Any]) -> dict[str, Any] | None:
    source_cache = policy["roots"]["source_cache"]["path"]
    shared_data = policy["roots"]["shared_data"]["path"]
    has_ubuntu = "/home/ubuntu" in text or "id -un" in text and "ubuntu" in text
    has_source_cache = source_cache in text
    has_shared_data = shared_data in text or "AGENT_DATA_ROOT" in text
    has_node_identity = "agentos-node" in text or "/home/agentos-node" in text
    direct_oracle_runner = bool(re.search(
        r"runs-on:\s*\[(?=[^\]]*self-hosted)(?=[^\]]*oracle)[^\]]*\]",
        text,
        re.IGNORECASE,
    ))
    explicit_node_user = bool(re.search(
        r"(?:id\s+-un[^\n]{0,80}agentos-node|User\s*=\s*agentos-node)",
        text,
        re.IGNORECASE,
    ))
    node_execution_proven = direct_oracle_runner or explicit_node_user
    user_systemd = "systemctl --user" in text or ".config/systemd/user" in text or "[Service]" in text
    bounded_group = any(marker in text for marker in policy["bounded_group_markers"])
    mutation = any(marker in text for marker in policy["mutation_markers"])
    interactive_hint = any(hint in rel.casefold() for hint in policy["ubuntu_required_path_hints"])

    if not any((has_ubuntu, has_source_cache, has_shared_data, has_node_identity, user_systemd, bounded_group)):
        return None

    tags: list[str] = []
    risk = "P2"
    classification = "identity-reference"

    if interactive_hint and has_ubuntu:
        classification = "ubuntu-required-candidate"
        tags.append("interactive-login-or-profile")
    if has_source_cache:
        tags.append("ubuntu-source-cache")
        risk = min(risk, "P1")
    if has_shared_data:
        tags.append("shared-runtime-data")
        classification = "shared-runtime-boundary"
        risk = "P1"
    if user_systemd:
        tags.append("user-systemd")
    if has_node_identity:
        tags.append("agentos-node-reference")
    if direct_oracle_runner:
        tags.append("direct-oracle-runner")
    if explicit_node_user:
        tags.append("explicit-agentos-node-user")
    if bounded_group:
        tags.append("explicit-agentos-group-boundary")

    # P0 is intentionally narrow: a file both touches the transitional shared
    # runtime, appears capable of mutation, crosses/mentions service identities,
    # and lacks an explicit group boundary. This is the class that has already
    # caused production PermissionError/recovery failures.
    if has_shared_data and mutation and node_execution_proven and not bounded_group:
        risk = "P0"
        classification = "unbounded-cross-owner-mutation"
        tags.append("implicit-group-risk")
    elif has_shared_data and mutation and user_systemd and not bounded_group:
        # user-systemd alone does not prove a cross-owner mutation. Hosted SSH
        # and ubuntu-owned installers commonly reference shared runtime paths
        # without crossing identities. Keep these visible for review, but do not
        # promote them to production P0 without explicit agentos-node evidence.
        risk = "P1"
        classification = "user-runtime-mutation-review"
        tags.append("identity-owner-unproven")

    return {
        "path": rel,
        "risk": risk,
        "classification": classification,
        "tags": sorted(set(tags)),
        "has_mutation_marker": mutation,
        "has_explicit_group_boundary": bounded_group,
    }


def build_inventory(root: Path = ROOT) -> dict[str, Any]:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for path in _tracked_files(root):
        rel = path.relative_to(root).as_posix()
        if not _under_review_root(rel, policy["review_roots"]):
            continue
        if _excluded(rel, policy.get("audit_excludes") or []):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        row = _classify(rel, text, policy)
        if row:
            rows.append(row)

    confirmed = policy.get("confirmed_migrations") or {}
    for row in rows:
        item = confirmed.get(row["path"])
        if item:
            status = str(item.get("status") or "pending")
            if status == "live_immutable_complete":
                row["risk"] = "P2"
                row["classification"] = "resolved-live-migration"
                row["resolved_status"] = status
                row["live_acceptance"] = item.get("live_acceptance") or {}
            else:
                row["risk"] = str(item["severity"])
                row["classification"] = "confirmed-migration"
            row["confirmed_reason"] = str(item["reason"])
            row["target_state"] = str(item["target"])

    rows.sort(key=lambda r: (r["risk"], r["path"]))
    counts = Counter(row["risk"] for row in rows)
    classes = Counter(row["classification"] for row in rows)
    return {
        "schema": "agentos.oracle-identity-boundary-audit/v1",
        "policy_version": policy["policy_version"],
        "summary": {
            "files_reviewed": len(rows),
            "p0": counts.get("P0", 0),
            "p1": counts.get("P1", 0),
            "p2": counts.get("P2", 0),
            "confirmed_migrations": sum(1 for row in rows if row["classification"] == "confirmed-migration"),
            "resolved_live_migrations": sum(1 for row in rows if row["classification"] == "resolved-live-migration"),
            "classifications": dict(sorted(classes.items())),
        },
        "findings": rows,
    }


def _markdown(payload: dict[str, Any]) -> str:
    s = payload["summary"]
    lines = [
        "# Oracle Identity Boundary Audit",
        "",
        f"- Policy: \`{payload['policy_version']}\`",
        f"- Findings: **{s['files_reviewed']}**",
        f"- P0: **{s['p0']}**",
        f"- P1: **{s['p1']}**",
        f"- P2: **{s['p2']}**",
        "",
        "| Risk | Classification | Path | Tags |",
        "|---|---|---|---|",
    ]
    for row in payload["findings"]:
        lines.append(
            f"| {row['risk']} | {row['classification']} | \`{row['path']}\` | "
            + ", ".join(row["tags"])
            + " |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out")
    parser.add_argument("--markdown-out")
    parser.add_argument("--fail-on-p0", action="store_true")
    args = parser.parse_args()

    payload = build_inventory()
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.json_out:
        Path(args.json_out).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    if args.markdown_out:
        Path(args.markdown_out).write_text(_markdown(payload), encoding="utf-8")

    if args.fail_on_p0 and payload["summary"]["p0"]:
        print(f"ORACLE_IDENTITY_BOUNDARY_AUDIT=FAIL p0={payload['summary']['p0']}")
        return 2
    print(
        "ORACLE_IDENTITY_BOUNDARY_AUDIT=PASS "
        f"p0={payload['summary']['p0']} p1={payload['summary']['p1']} p2={payload['summary']['p2']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
