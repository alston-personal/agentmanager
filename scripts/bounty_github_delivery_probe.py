#!/usr/bin/env python3
"""Bounty GitHub delivery gate: token-scoped preflight and durable action receipt.

This is a capability check, NOT a workflow dispatcher. Uses the already governed
ONE executor and respects GitHub's app installation authorization boundary.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ProbeReceipt:
    capability: str
    outcome: str
    http_status: int | None
    reason: str
    repository: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)


def classify_http(capability: str, repository: str, status: int | None) -> ProbeReceipt:
    if status == 204 or status == 200:
        return ProbeReceipt(capability, "READY", status, "permission_probe_passed", repository)
    if status in (401, 403):
        return ProbeReceipt(capability, "AUTH_REQUIRED", status, "github_integration_permission_denied", repository)
    if status == 404:
        return ProbeReceipt(capability, "NOT_FOUND", status, "repository_not_visible_or_absent", repository)
    if status in (429, 500, 502, 503, 504):
        return ProbeReceipt(capability, "RETRYABLE", status, "github_transient_failure", repository)
    return ProbeReceipt(capability, "BLOCKED", status, "unhandled_github_response", repository)


def probe_repository(repository: str, token: str, opener=urllib.request.urlopen) -> ProbeReceipt:
    """Read-only authentication check. Never creates comments, PRs, or permissions."""
    if not token:
        return ProbeReceipt("github.repo.read", "AUTH_REQUIRED", None, "github_token_missing", repository)
    request = urllib.request.Request(
        "https://api.github.com/repos/" + repository,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "agentos-bounty-delivery-probe",
        },
    )
    try:
        response = opener(request, timeout=15)
        with response:
            status = response.status
        return classify_http("github.repo.read", repository, status)
    except urllib.error.HTTPError as error:
        return classify_http("github.repo.read", repository, error.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        return ProbeReceipt("github.repo.read", "RETRYABLE", None, "github_transport_error", repository)


def persist_receipt(path: str, receipt: ProbeReceipt) -> None:
    """Atomically checkpoint one probe receipt without exposing credentials."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                         prefix=".bounty-receipt-", delete=False) as handle:
            temp_name = handle.name
            handle.write(receipt.to_json() + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="owner/repo")
    parser.add_argument("--dry-run", action="store_true", help="emit local token readiness without contacting GitHub")
    parser.add_argument("--receipt-file", help="optional path to atomic durable JSON receipt")
    args = parser.parse_args()
    if len(args.repo.split("/")) != 2 or not all(args.repo.split("/")):
        parser.error("--repo must be owner/repo")
    token = os.environ.get("AGENTOS_GITHUB_TOKEN", "")
    receipt = (
        ProbeReceipt("github.repo.read", "UNVERIFIED" if token else "AUTH_REQUIRED",
                     None, "dry_run_no_api_request" if token else "github_token_missing", args.repo)
        if args.dry_run else probe_repository(args.repo, token)
    )
    if args.receipt_file:
        persist_receipt(args.receipt_file, receipt)
    print(receipt.to_json())
    return 0 if receipt.outcome in ("READY", "UNVERIFIED") else 2


if __name__ == "__main__":
    raise SystemExit(main())
