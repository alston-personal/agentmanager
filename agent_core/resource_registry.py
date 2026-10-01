from __future__ import annotations

import json
import os
import socket
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA_ROOT = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
REGISTRY_PATH = DATA_ROOT / "resources" / "registry.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_registry(path: Path = REGISTRY_PATH) -> dict:
    if not path.exists():
        return {"schema_version": "0.1", "updated_at": None, "resources": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    # Backward-compatible with an early direct-id object layout.
    if "resources" not in data:
        candidates = {k: v for k, v in data.items() if isinstance(v, dict) and "://" in k}
        if candidates:
            data = {"schema_version": "0.1", "updated_at": None, "resources": candidates}
        else:
            data.setdefault("resources", {})
    data.setdefault("schema_version", "0.1")
    return data


def save_registry(data: dict, path: Path = REGISTRY_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _now()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def get(resource_id: str, path: Path = REGISTRY_PATH) -> dict | None:
    return load_registry(path).get("resources", {}).get(resource_id)


def list_resources(kind: str | None = None, path: Path = REGISTRY_PATH) -> list[dict]:
    values = list(load_registry(path).get("resources", {}).values())
    if kind:
        values = [v for v in values if v.get("kind") == kind]
    return sorted(values, key=lambda v: v.get("id", ""))


def register(resource_id: str, kind: str, declared: dict[str, Any], ttl_seconds: int = 86400,
             *, replace: bool = False, path: Path = REGISTRY_PATH) -> dict:
    data = load_registry(path)
    resources = data.setdefault("resources", {})
    current = resources.get(resource_id)
    if current and not replace:
        raise ValueError(f"resource already exists: {resource_id}")
    observed = current.get("observed", {}) if current else {}
    verification = current.get("verification", {}) if current else {}
    verification.setdefault("status", "unverified")
    verification.setdefault("last_verified_at", None)
    verification["ttl_seconds"] = int(ttl_seconds)
    verification.setdefault("errors", [])
    resource = {
        "id": resource_id,
        "kind": kind,
        "declared": declared,
        "observed": observed,
        "verification": verification,
    }
    resources[resource_id] = resource
    save_registry(data, path)
    return resource


def _git(repo: str, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", "-c", f"safe.directory={repo}", "-C", repo, *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=8,
    )
    return proc.returncode, proc.stdout.strip() if proc.returncode == 0 else proc.stderr.strip()


def _set_verification(resource: dict, *, observed: dict[str, Any], errors: list[str]) -> dict:
    _set_verification(resource, observed=observed, errors=errors)
    return resource


def resource_ready(resource_id: str, path: Path = REGISTRY_PATH) -> tuple[bool, str]:
    resource = get(resource_id, path)
    if not resource:
        return False, "RESOURCE_NOT_REGISTERED"
    verification = resource.get("verification", {})
    if verification.get("status") != "verified":
        return False, "RESOURCE_NOT_READY"
    return True, "RESOURCE_READY"


def verify_mount(resource_id: str, path: Path = REGISTRY_PATH) -> dict:
    data = load_registry(path)
    resource = data.get("resources", {}).get(resource_id)
    if not resource:
        raise KeyError(resource_id)
    if resource.get("kind") != "storage":
        raise ValueError(f"not a storage resource: {resource_id}")

    declared = resource.get("declared", {})
    mountpoint = str(declared.get("mountpoint") or "").strip()
    service = str(declared.get("service") or "").strip()
    expected_fstype = str(declared.get("fstype") or "").strip()
    errors: list[str] = []
    observed: dict[str, Any] = {"mountpoint": mountpoint}

    if not mountpoint:
        errors.append("mountpoint: missing")
    else:
        proc = subprocess.run(
            ["mountpoint", "-q", mountpoint],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        observed["mounted"] = proc.returncode == 0
        if proc.returncode != 0:
            errors.append("mountpoint: not mounted")
        else:
            fm = subprocess.run(
                ["findmnt", "-n", "-o", "FSTYPE", "--target", mountpoint],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            fstype = fm.stdout.strip() if fm.returncode == 0 else ""
            observed["fstype"] = fstype
            if expected_fstype and fstype != expected_fstype:
                errors.append(f"fstype: expected {expected_fstype}, got {fstype or 'unknown'}")

    if service:
        svc = subprocess.run(
            ["systemctl", "--user", "is-active", "--quiet", service],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        observed["service"] = {"name": service, "active": svc.returncode == 0}
        if svc.returncode != 0:
            errors.append(f"service: inactive: {service}")

    _set_verification(resource, observed=observed, errors=errors)
    data["resources"][resource_id] = resource
    save_registry(data, path)
    return resource


def verify_site(resource_id: str, path: Path = REGISTRY_PATH) -> dict:
    data = load_registry(path)
    resource = data.get("resources", {}).get(resource_id)
    if not resource:
        raise KeyError(resource_id)
    if resource.get("kind") != "site":
        raise ValueError(f"not a site resource: {resource_id}")

    d = resource.get("declared", {})
    domain = d.get("domain") or resource_id.removeprefix("site://")
    errors: list[str] = []
    observed: dict[str, Any] = {}

    try:
        observed["dns"] = sorted({item[4][0] for item in socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)})
    except Exception as exc:
        errors.append(f"dns: {exc}")

    try:
        req = urllib.request.Request(f"https://{domain}/", method="HEAD", headers={"User-Agent": "AgentOS-Node/0.1"})
        with urllib.request.urlopen(req, timeout=10) as response:
            observed["http"] = {
                "status": response.status,
                "server": response.headers.get("Server"),
                "content_type": response.headers.get("Content-Type"),
            }
    except Exception as exc:
        errors.append(f"https: {exc}")

    paths: dict[str, Any] = {}
    for key in ("repo_path", "source_path", "dist_path", "nginx_config"):
        raw = d.get(key)
        if not raw:
            continue
        p = Path(raw)
        paths[key] = {
            "path": raw,
            "exists": p.exists(),
            "readable": os.access(p, os.R_OK),
            "writable": os.access(p, os.W_OK),
        }
    observed["paths"] = paths

    repo = d.get("repo_path")
    if repo and Path(repo).is_dir():
        git_state: dict[str, Any] = {}
        for name, args in {
            "branch": ("branch", "--show-current"),
            "commit": ("rev-parse", "HEAD"),
            "origin": ("remote", "get-url", "origin"),
        }.items():
            code, output = _git(repo, *args)
            if code == 0:
                git_state[name] = output
            else:
                errors.append(f"git.{name}: {output}")
        observed["git"] = git_state

    resource["observed"] = observed
    resource["verification"] = {
        **resource.get("verification", {}),
        "status": "verified" if not errors else "degraded",
        "last_verified_at": _now(),
        "errors": errors,
    }
    data["resources"][resource_id] = resource
    save_registry(data, path)
    return resource
