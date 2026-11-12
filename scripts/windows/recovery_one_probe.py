#!/usr/bin/env python3
"""Minimal read-only ONE recovery-lane probe.

Independently executable using Python stdlib: it must not import the normal
Thin Client runtime or execute remotely returned instructions. This is NOT a
full rescue updater or proof of an independently installed Recovery service.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TENANT_REALM = re.compile(r"realm-u-[0-9a-f]{24}\Z")
NODE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
ONE_ORIGINS = ("https://agentos.milkcat.org", "https://studio.milkcat.org/dashboard/api/agentos")
RESULT_SCHEMA = "agentos.recovery-probe/v1"


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("invalid_recovery_config")
    for key in ("one_url", "node_id", "realm_id", "node_token"):
        if not isinstance(config.get(key), str) or not config[key]:
            raise ValueError("missing_recovery_identity")
    parsed = urllib.parse.urlsplit(config["one_url"])
    if (parsed.scheme != "https" or parsed.username or parsed.password
            or parsed.query or parsed.fragment
            or config["one_url"].rstrip("/") not in ONE_ORIGINS):
        raise ValueError("recovery_one_origin_not_trusted")
    if not NODE_ID.fullmatch(config["node_id"]):
        raise ValueError("invalid_recovery_node")
    if not NODE_ID.fullmatch(config["realm_id"]) and not TENANT_REALM.fullmatch(config["realm_id"]):
        raise ValueError("invalid_recovery_realm")
    if len(config["node_token"]) < 16 or any(c.isspace() for c in config["node_token"]):
        raise ValueError("invalid_recovery_token")
    return config


def bootstrap_url(config):
    config = validate_config(config)
    if TENANT_REALM.fullmatch(config["realm_id"]):
        if config["one_url"].rstrip("/") != "https://agentos.milkcat.org":
            raise ValueError("tenant_recovery_requires_agentos_origin")
        base = "https://agentos.milkcat.org/v1/realms/" + config["realm_id"] + "/bootstrap"
    else:
        base = config["one_url"].rstrip("/") + "/v1/bootstrap"
    return base + "?" + urllib.parse.urlencode({"node_id": config["node_id"]})


class NoRecoveryRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward the recovery Bearer token to a redirect destination."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("recovery_redirect_denied")


def probe_one(config, *, opener=None, timeout=8):
    """Authenticated ONE bootstrap read; never execute returned instructions."""
    config = validate_config(config)
    req = urllib.request.Request(
        bootstrap_url(config),
        headers={
            "Authorization": "Bearer " + config["node_token"],
            "Accept": "application/json",
            "User-Agent": "AgentOS-Recovery-Probe/1",
        },
        method="GET",
    )
    open_fn = opener or urllib.request.build_opener(NoRecoveryRedirect()).open
    with open_fn(req, timeout=timeout) as response:
        if getattr(response, "status", 200) != 200:
            raise RuntimeError("recovery_bootstrap_http_failure")
        raw = response.read(131073)
        if len(raw) > 131072:
            raise ValueError("recovery_bootstrap_oversize")
        payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("recovery_bootstrap_not_object")
    # A JSON dictionary alone is not a trusted recovery manifest or a signed
    # package. This probe only attests authenticated transport round-trip.
    return {
        "schema": RESULT_SCHEMA,
        "node_id": config["node_id"],
        "realm_id": config["realm_id"],
        "one_transport_roundtrip": True,
        "adapter_download_verified": False,
        "recovery_update_authorized": False,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }


def write_status(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".recovery-probe-", suffix=".json",
                                dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--status", required=True)
    args = parser.parse_args()
    try:
        config = json.loads(Path(args.config).read_text(encoding="utf-8-sig"))
        result = probe_one(config)
        exit_code = 0
    except Exception as exc:
        result = {
            "schema": RESULT_SCHEMA,
            "one_transport_roundtrip": False,
            "adapter_download_verified": False,
            "recovery_update_authorized": False,
            "error_class": type(exc).__name__,
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }
        exit_code = 1
    write_status(args.status, result)
    print(json.dumps(result, sort_keys=True))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
