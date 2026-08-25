from __future__ import annotations

import json
import os
import socket
import subprocess
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class Freshness:
    state: str
    age_seconds: int | None
    ttl_seconds: int


class ResourceRegistry:
    """Persistent, query-first registry for node-observed environment resources.

    Logic lives in agentmanager; mutable registry state lives under AGENT_DATA_ROOT.
    Resource IDs are URI-like stable identifiers such as site://studio.milkcat.org.
    """

    def __init__(self, path: str | Path | None = None):
        data_root = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
        self.path = Path(path) if path else data_root / "resources" / "registry.json"

    def _empty(self) -> dict[str, Any]:
        return {"schema_version": "0.1", "resources": {}}

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._empty()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("resources"), dict):
            raise ValueError(f"Invalid resource registry: {self.path}")
        return data

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def list(self, kind: str | None = None) -> list[dict[str, Any]]:
        entries = list(self.load()["resources"].values())
        if kind:
            entries = [entry for entry in entries if entry.get("kind") == kind]
        return sorted(entries, key=lambda item: item.get("id", ""))

    def get(self, resource_id: str) -> dict[str, Any] | None:
        return self.load()["resources"].get(resource_id)

    def register(
        self,
        resource_id: str,
        kind: str,
        declared: dict[str, Any],
        *,
        ttl_seconds: int = 86400,
        labels: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if "://" not in resource_id:
            raise ValueError("resource_id must be URI-like, e.g. site://example.com")
        data = self.load()
        existing = data["resources"].get(resource_id, {})
        entry = {
            "id": resource_id,
            "kind": kind,
            "labels": labels or existing.get("labels", {}),
            "declared": declared,
            "observed": existing.get("observed", {}),
            "verification": existing.get("verification", {
                "status": "unverified",
                "last_verified_at": None,
                "ttl_seconds": ttl_seconds,
                "errors": [],
            }),
            "registered_at": existing.get("registered_at", _utc_now()),
            "updated_at": _utc_now(),
        }
        entry["verification"]["ttl_seconds"] = ttl_seconds
        data["resources"][resource_id] = entry
        self.save(data)
        return entry

    def freshness(self, entry: dict[str, Any]) -> Freshness:
        verification = entry.get("verification", {})
        ttl = int(verification.get("ttl_seconds", 86400))
        verified = _parse_time(verification.get("last_verified_at"))
        if verified is None:
            return Freshness("unverified", None, ttl)
        age = max(0, int((datetime.now(timezone.utc) - verified.astimezone(timezone.utc)).total_seconds()))
        return Freshness("fresh" if age <= ttl else "stale", age, ttl)

    def describe(self, resource_id: str) -> dict[str, Any] | None:
        entry = self.get(resource_id)
        if not entry:
            return None
        result = dict(entry)
        fresh = self.freshness(entry)
        result["freshness"] = {
            "state": fresh.state,
            "age_seconds": fresh.age_seconds,
            "ttl_seconds": fresh.ttl_seconds,
        }
        return result

    def verify_site(self, resource_id: str, timeout: float = 8.0) -> dict[str, Any]:
        entry = self.get(resource_id)
        if not entry:
            raise KeyError(resource_id)
        if entry.get("kind") != "site":
            raise ValueError(f"verify_site only supports kind=site, got {entry.get('kind')}")
        declared = entry.get("declared", {})
        domain = declared.get("domain") or resource_id.split("://", 1)[1]
        errors: list[str] = []
        observed: dict[str, Any] = {"observed_at": _utc_now(), "hostname": socket.gethostname()}

        try:
            observed["dns"] = sorted({item[4][0] for item in socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)})
        except Exception as exc:
            errors.append(f"dns: {exc}")

        try:
            req = urllib.request.Request(f"https://{domain}/", method="HEAD", headers={"User-Agent": "AgentOS-Node/0.3"})
            with urllib.request.urlopen(req, timeout=timeout) as res:
                observed["http"] = {
                    "status": res.status,
                    "server": res.headers.get("Server"),
                    "content_type": res.headers.get("Content-Type"),
                }
        except Exception as exc:
            errors.append(f"http: {exc}")

        for key in ("source_path", "dist_path", "nginx_config"):
            value = declared.get(key)
            if value:
                path = Path(value)
                observed.setdefault("paths", {})[key] = {
                    "exists": path.exists(),
                    "readable": os.access(path, os.R_OK),
                    "writable": os.access(path, os.W_OK),
                }

        repo_path = declared.get("repo_path")
        if repo_path and Path(repo_path, ".git").exists():
            try:
                observed["git"] = {
                    "commit": subprocess.check_output(["git", "-C", repo_path, "rev-parse", "HEAD"], text=True).strip(),
                    "branch": subprocess.check_output(["git", "-C", repo_path, "branch", "--show-current"], text=True).strip(),
                    "origin": subprocess.check_output(["git", "-C", repo_path, "remote", "get-url", "origin"], text=True).strip(),
                }
            except Exception as exc:
                errors.append(f"git: {exc}")

        data = self.load()
        current = data["resources"][resource_id]
        current["observed"] = observed
        current["verification"] = {
            **current.get("verification", {}),
            "status": "verified" if not errors else "degraded",
            "last_verified_at": _utc_now(),
            "errors": errors,
        }
        current["updated_at"] = _utc_now()
        data["resources"][resource_id] = current
        self.save(data)
        return self.describe(resource_id) or current
