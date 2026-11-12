"""ONE read-only deployment inspection for two fixed site targets.

No shell input, deploy, reload, sudo, config dump, Nginx mutation or trusted
user-provided runtime evidence. Deliberately fail-closed when live state cannot
be attested. The standalone deployment gate remains non-executing.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Mapping

from agent_core.executor_job_contract import validate_executor_job
from agentos_node.executor_job_adapter import DEFAULT_PROVIDERS, ExecutorJobProviderRegistry

JOBS = {
    "deployment.agentos.inspect": "site://agentos.milkcat.org",
    "deployment.studio.inspect": "site://studio.milkcat.org",
}
CLASS = "oracle-deployment-inspector"
MARKER = "studio-web-production-root/v1"
SITEFILE = Path("/etc/nginx/sites-enabled/studio.milkcat.org")
SITEFILE_TARGETS = frozenset((
    Path("/etc/nginx/sites-enabled/studio.milkcat.org"),
    Path("/etc/nginx/sites-available/studio.milkcat.org"),
))

def _run(argv: list[str], *, timeout: int = 8) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)

def _http(host: str, path: str) -> tuple[int, str] | None:
    """Use only fixed localhost-bound TLS origins. Do not emit response bodies."""
    try:
        p = _run([
            "/usr/bin/curl", "--silent", "--show-error", "--max-time", "8",
            "--max-filesize", "524288", "--resolve", f"{host}:443:127.0.0.1",
            "--write-out", "\n%{http_code}", f"https://{host}{path}",
        ], timeout=10)
        if p.returncode:
            return None
        body, sep, status = p.stdout.rpartition("\n")
        if not sep or not status.isdigit():
            return None
        return int(status), body
    except (OSError, subprocess.TimeoutExpired):
        return None

def _status(kind: str) -> dict[str, Any]:
    # Only registered local kinds are possible; never derive a command or path
    # from user input, a domain in an incoming request, or an untrusted config.
    if kind == "deployment.studio.inspect":
        root_class = "unknown"
        try:
            if SITEFILE.resolve(strict=True) in SITEFILE_TARGETS:
                source = SITEFILE.read_text(encoding="utf-8")
                # This is only an on-disk site-file observation, NOT proof of
                # the effective loaded Nginx configuration.
                if re.search(r"(?m)^\s*root\s+/home/ubuntu/zeus-writer/website/dist\s*;", source):
                    root_class = "legacy"
                elif re.search(r"(?m)^\s*root\s+/home/ubuntu/studio-web/dist\s*;", source):
                    root_class = "studio"
                else:
                    root_class = "other"
        except (OSError, UnicodeError, ValueError):
            pass
        public = _http("studio.milkcat.org", "/.well-known/studio-root-authority.txt")
        canary = public is not None and public[0] == 200 and public[1].strip() == MARKER
        # No privilege to attest effective nginx -T and old-root writers:
        # a passing canary must not be mistaken for completed cutover.
        classification = ("STUDIO_LEGACY_SITEFILE" if root_class == "legacy"
            else "STUDIO_SITEFILE_UNAVAILABLE" if root_class == "unknown"
            else "STUDIO_CANARY_MISMATCH" if not canary
            else "STUDIO_EFFECTIVE_VHOST_UNVERIFIED")
        return {"verdict": "FAIL", "classification": classification,
                "successful": False, "authorized": True, "routable": True,
                "executor_available": True, "credential_exposed": False}
    if kind == "deployment.agentos.inspect":
        try:
            proc = _run([
                "/usr/bin/systemctl", "--user", "show", "agentos-control-plane.service",
                "--property=ActiveState", "--value",
            ])
            active = proc.returncode == 0 and proc.stdout.strip() == "active"
        except (OSError, subprocess.TimeoutExpired):
            active = False
        public = _http("agentos.milkcat.org", "/")
        # Health alone is not release parity, login, OAuth, Realm or rollback.
        classification = ("AGENTOS_CONSOLE_SERVICE_UNAVAILABLE" if not active
            else "AGENTOS_CONSOLE_PUBLIC_UNAVAILABLE" if public is None or public[0] != 200
            else "AGENTOS_CONSOLE_RELEASE_UNVERIFIED")
        return {"verdict": "FAIL", "classification": classification,
                "successful": False, "authorized": True, "routable": True,
                "executor_available": True, "credential_exposed": False}
    raise ValueError("unsupported fixed deployment inspection target")

def run_deployment_inspection(request: Mapping[str, Any]) -> dict[str, Any]:
    spec = validate_executor_job(request)
    if spec.job_type not in JOBS or spec.executor_class != CLASS:
        return {"verdict": "FAIL", "classification": "DEPLOYMENT_INSPECT_CONTRACT_MISMATCH",
                "successful": False, "authorized": False, "routable": False,
                "executor_available": False, "credential_exposed": False}
    return _status(spec.job_type)

def register_deployment_inspection_providers(
    registry: ExecutorJobProviderRegistry = DEFAULT_PROVIDERS,
) -> bool:
    for job_type in JOBS:
        existing = registry.get(job_type)
        provider_id = "deployment-inspect-" + job_type.removeprefix("deployment.")
        if existing is not None:
            if existing.provider_id != provider_id or existing.executor_class != CLASS:
                raise RuntimeError("Deployment inspector bound to a different provider")
            continue
        registry.register(job_type=job_type, provider_id=provider_id,
                          executor_class=CLASS, handler=run_deployment_inspection)
    return True
