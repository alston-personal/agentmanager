"""Hermes bounded, read-only GitHub technology reconnaissance.

This CLI is a capability implementation, NOT a scheduler, worker dispatch, or an
AgentOS operating receipt. Any runtime bridge must pass through existing ONE.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from agent_core.hermes_scan_policy import ScanSignals, propose_scan

DEFAULT_REPOS = (
    "paperclipai/paperclip", "gastownhall/gastown", "max-sixty/worktrunk",
    "getpaseo/paseo", "KKKKhazix/agent-autoloop", "CopilotKit/OpenBot",
    "nightly-labs/openbot", "stablyai/orca", "orca-cli/orca",
    "JustVugg/colibri",
)
SCHEMA = "agentos.hermes-technology-scan/v1"
MAX_REPOS = 25
MAX_RESPONSE_BYTES = 350_000
BASE_URL = "https://api.github.com/repos/"


def normalized_repo(value: str) -> str:
    parts = value.strip().split("/")
    if len(parts) != 2 or any(not p or len(p) > 100 for p in parts):
        raise ValueError("invalid_repository")
    if any(not all(c.isalnum() or c in "-_." for c in p) for p in parts):
        raise ValueError("invalid_repository")
    if any(p in (".", "..") for p in parts):
        raise ValueError("invalid_repository")
    return "/".join(parts)


def github_repo_get(repo: str, *, token: str = "", timeout: int = 12) -> dict[str, Any]:
    """Only access the pinned public GitHub REST domain; no URL from repo content."""
    repo = normalized_repo(repo)
    url = BASE_URL + "/".join(urllib.parse.quote(p, safe="") for p in repo.split("/"))
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "agentos-hermes-readonly",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers, method="GET")
    # Avoid following untrusted redirect destinations.
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as resp:
            if resp.status != 200:
                raise RuntimeError("github_http_non_200")
            raw = resp.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise RuntimeError("github_response_too_large")
            data = json.loads(raw)
    except (urllib.error.URLError, ValueError) as exc:
        raise RuntimeError("github_metadata_unavailable") from exc
    if not isinstance(data, dict):
        raise RuntimeError("github_response_invalid")
    return data


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("github_redirect_not_allowed")


def evaluate(repo: str, metadata: dict[str, Any], *, now: str) -> dict[str, Any]:
    """Deterministic candidate record, conservative about unverified capabilities."""
    canonical = normalized_repo(repo)
    full_name = str(metadata.get("full_name") or "")
    if full_name.lower() != canonical.lower():
        raise ValueError("github_identity_mismatch")
    updated = str(metadata.get("pushed_at") or "")
    license_obj = metadata.get("license")
    license_id = license_obj.get("spdx_id") if isinstance(license_obj, dict) else None
    license_id = license_id or "UNKNOWN"
    result = {
        "repo": full_name,
        "source_url": "https://github.com/" + canonical,
        "observed_at": now,
        "upstream_pushed_at": updated or None,
        "archived": bool(metadata.get("archived")),
        "disabled": bool(metadata.get("disabled")),
        "license_spdx": license_id,
        "stargazers_count": int(metadata.get("stargazers_count") or 0),
        "default_branch": str(metadata.get("default_branch") or ""),
        "description": str(metadata.get("description") or "")[:500],
        "classification": "EXPERIMENT_CANDIDATE",
        "adoption_authorized": False,
        "requires_existing_capability_comparison": True,
        "requires_license_and_security_review": True,
        "evidence_level": "GITHUB_METADATA_ONLY",
    }
    if result["archived"] or result["disabled"]:
        result["classification"] = "REJECTED"
    elif license_id in ("UNKNOWN", "NOASSERTION", "OTHER"):
        result["classification"] = "DESIGN_REFERENCE"
    result["fingerprint"] = hashlib.sha256(
        json.dumps({k:result[k] for k in ("repo","upstream_pushed_at","license_spdx","classification")},
                   sort_keys=True).encode("utf-8")
    ).hexdigest()
    return result


def run_scan(repos: list[str], fetch: Callable[[str], dict[str, Any]], *,
             old_fingerprints: dict[str, str] | None = None,
             now: datetime | None = None) -> dict[str, Any]:
    if len(repos) > MAX_REPOS:
        raise ValueError("too_many_repositories")
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    seen: set[str] = set()
    findings = []
    failures = []
    for raw in repos:
        repo = normalized_repo(raw)
        key = repo.casefold()
        if key in seen:
            continue
        seen.add(key)
        try:
            finding = evaluate(repo, fetch(repo), now=now.isoformat())
        except (ValueError, RuntimeError, KeyError, TypeError) as exc:
            failures.append({"repo":repo, "error_class":type(exc).__name__})
            continue
        finding["changed_since_last_scan"] = (
            (old_fingerprints or {}).get(key) != finding["fingerprint"]
        )
        findings.append(finding)
    return {
        "schema": SCHEMA, "role_id": "research.hermes",
        "employee_id": "hermes-technology-scout",
        "scan_at": now.isoformat(), "findings":findings, "failures":failures,
        "source_count":len(seen), "candidate_count":len(findings),
        "changed_count":sum(x["changed_since_last_scan"] for x in findings),
        "classification_scope":"PUBLIC_METADATA_ONLY",
        "runtime_receipt":False,
        "work_item_created":False,
    }


def atomic_json_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".hermes-", delete=False) as temp:
        filename = temp.name
        json.dump(value, temp, ensure_ascii=False, indent=2, sort_keys=True)
        temp.write("\n")
        temp.flush()
        os.fsync(temp.fileno())
    os.replace(filename, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes read-only GitHub metadata scan")
    parser.add_argument("--state-dir", required=True,
                        help="Existing explicitly authorized role-private directory")
    parser.add_argument("--repo", action="append", default=[],
                        help="public owner/repo; repeated, max 25")
    parser.add_argument("--dry-run", action="store_true", help="Do not persist state")
    args = parser.parse_args()
    directory = Path(args.state_dir).expanduser().resolve(strict=True)
    if not directory.is_dir():
        parser.error("state-dir must be an existing role-private directory")
    state_file = directory / "hermes-scan-state.json"
    previous = {}
    if state_file.exists():
        previous = json.loads(state_file.read_text(encoding="utf-8"))
        if not isinstance(previous, dict) or previous.get("schema") != "agentos.hermes-state/v1":
            parser.error("invalid existing Hermes state")
    now = datetime.now(timezone.utc)
    last = previous.get("last_scan_at")
    last_dt = datetime.fromisoformat(last) if isinstance(last, str) else None
    signals = ScanSignals(
        meaningful_findings=int(previous.get("last_meaningful_findings", 0)),
        consecutive_empty_scans=int(previous.get("consecutive_empty_scans", 0)),
    )
    plan = propose_scan(now=now, last_scan_at=last_dt, signals=signals)
    if not args.dry_run and not plan.should_run:
        print(json.dumps({"status":"not_due", "next_eligible_at":plan.next_eligible_at,
                          "reason":plan.reason}))
        return 0
    repos = args.repo or list(DEFAULT_REPOS)
    report = run_scan(repos, lambda r: github_repo_get(r, token=os.environ.get("GITHUB_TOKEN","")),
                      old_fingerprints=previous.get("fingerprints",{}), now=now)
    report["next_scan_advisory"] = {
        "interval_hours":plan.interval_hours, "reason":plan.reason
    }
    if not args.dry_run:
        # On a partial metadata failure preserve prior fingerprints and do not erase learning.
        fingerprints = dict(previous.get("fingerprints", {}))
        fingerprints.update({x["repo"].casefold():x["fingerprint"] for x in report["findings"]})
        empty = 0 if report["changed_count"] else int(previous.get("consecutive_empty_scans",0))+1
        state = {"schema":"agentos.hermes-state/v1","last_scan_at":now.isoformat(),
                 "consecutive_empty_scans":empty, "last_meaningful_findings":0,
                 "fingerprints":fingerprints}
        atomic_json_write(directory / "hermes-latest-scan.json", report)
        atomic_json_write(state_file, state)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if not report["failures"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
