"""Read-only LayoutLib production parity provider.

Compares the immutable canonical v0.7.9 release snapshot with the bytes served
at the public Layout Lab route. This provider never deploys, writes runtime
state, changes services, or accepts caller-supplied paths/URLs.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Mapping
from urllib.request import Request, urlopen

from agent_core.executor_job_contract import validate_executor_job
from agentos_node.executor_job_adapter import DEFAULT_PROVIDERS, ExecutorJobProviderRegistry

JOB_TYPE = "layoutlib.production.parity.inspect"
EXECUTOR_CLASS = "layoutlib-parity-inspector"
PROVIDER_ID = "layoutlib-production-parity-v1"
DEFAULT_REPO_ROOT = Path("/home/agentos-node/projects/layoutlib")
RELEASE = "v0.7.9"
PUBLIC_BASE = "https://studio.milkcat.org/layout-lab/"


def _failure(classification: str, **extra: Any) -> dict[str, Any]:
    return {
        "verdict": "FAIL",
        "classification": classification,
        "executor_available": True,
        "routable": True,
        "authorized": True,
        "successful": False,
        "credential_exposed": False,
        **extra,
    }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fetch(url: str, *, timeout: float = 20.0) -> tuple[int, bytes]:
    req = Request(url, headers={"User-Agent": "AgentOS-LayoutLib-Parity/1.0"})
    with urlopen(req, timeout=timeout) as response:
        return int(getattr(response, "status", 200) or 200), response.read()


def inspect_layoutlib_production_parity(
    request: Mapping[str, Any],
    *,
    repo_root: str | Path = DEFAULT_REPO_ROOT,
    public_base: str = PUBLIC_BASE,
) -> dict[str, Any]:
    spec = validate_executor_job(request)
    if spec.job_type != JOB_TYPE or spec.executor_class != EXECUTOR_CLASS:
        return _failure("LAYOUTLIB_PARITY_CONTRACT_MISMATCH")

    root = Path(repo_root)
    manifest_path = root / "release" / RELEASE / "manifest.json"
    if not manifest_path.is_file():
        return _failure("LAYOUTLIB_RELEASE_MANIFEST_MISSING", layoutlib_release=RELEASE)

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return _failure("LAYOUTLIB_RELEASE_MANIFEST_INVALID", layoutlib_release=RELEASE)

    entries = manifest.get("files")
    if manifest.get("release") != RELEASE or not isinstance(entries, list) or not entries:
        return _failure("LAYOUTLIB_RELEASE_MANIFEST_INVALID", layoutlib_release=RELEASE)

    try:
        observed_head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except Exception:
        observed_head = ""

    matched = 0
    public_root_http = 0
    for item in entries:
        if not isinstance(item, dict):
            return _failure("LAYOUTLIB_RELEASE_MANIFEST_INVALID", layoutlib_release=RELEASE)
        rel = str(item.get("destination") or "")
        expected = str(item.get("sha256") or "")
        if not rel.startswith(f"release/{RELEASE}/") or len(expected) != 64:
            return _failure("LAYOUTLIB_RELEASE_MANIFEST_INVALID", layoutlib_release=RELEASE)

        local = root / rel
        if not local.is_file() or _sha256(local.read_bytes()) != expected:
            return _failure(
                "LAYOUTLIB_CANONICAL_RELEASE_CORRUPT",
                layoutlib_release=RELEASE,
                layoutlib_manifest_files=len(entries),
                layoutlib_matching_files=matched,
                observed_head=observed_head,
            )

        name = Path(rel).name
        url = public_base if name == "layoutlab_v0_5.html" else public_base.rstrip("/") + "/" + name
        try:
            status, body = _fetch(url)
        except Exception:
            return _failure(
                "LAYOUTLIB_PUBLIC_FETCH_FAILED",
                layoutlib_release=RELEASE,
                layoutlib_manifest_files=len(entries),
                layoutlib_matching_files=matched,
                observed_head=observed_head,
            )

        if name == "layoutlab_v0_5.html":
            public_root_http = status
        if status != 200 or _sha256(body) != expected:
            return _failure(
                "LAYOUTLIB_PRODUCTION_PARITY_MISMATCH",
                layoutlib_release=RELEASE,
                layoutlib_manifest_files=len(entries),
                layoutlib_matching_files=matched,
                layoutlib_public_http=public_root_http,
                layoutlib_parity="MISMATCH",
                observed_head=observed_head,
            )
        matched += 1

    return {
        "verdict": "PASS",
        "classification": "LAYOUTLIB_PRODUCTION_PARITY_EXACT",
        "executor_available": True,
        "routable": True,
        "authorized": True,
        "successful": True,
        "credential_exposed": False,
        "layoutlib_release": RELEASE,
        "layoutlib_manifest_files": len(entries),
        "layoutlib_matching_files": matched,
        "layoutlib_public_http": public_root_http,
        "layoutlib_parity": "EXACT",
        "observed_head": observed_head,
    }


def register_layoutlib_parity_provider(
    registry: ExecutorJobProviderRegistry = DEFAULT_PROVIDERS,
) -> bool:
    if registry.get(JOB_TYPE) is not None:
        return False
    registry.register(
        job_type=JOB_TYPE,
        provider_id=PROVIDER_ID,
        executor_class=EXECUTOR_CLASS,
        handler=inspect_layoutlib_production_parity,
    )
    return True
