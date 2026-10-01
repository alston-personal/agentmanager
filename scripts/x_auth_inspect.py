#!/usr/bin/env python3
"""Read-only X OAuth identity probe CLI.

No Post is created and no media is uploaded. Secret values are never printed.
"""
from __future__ import annotations

import argparse
import json
import os

from runtime_core.x_auth_probe import CREDENTIAL_KEYS, inspect_x_auth


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-username", default="")
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()

    credentials = {name: str(os.environ.get(name) or "") for name in CREDENTIAL_KEYS}
    result = inspect_x_auth(
        credentials,
        expected_username=args.expected_username,
        timeout=args.timeout,
    )
    print(json.dumps(result, ensure_ascii=False))

    if result.get("authentication_success") is True:
        return 0
    status = str(result.get("status") or "UNKNOWN")
    if status == "AUTH_REQUIRED":
        return 2
    if status in {"ENTITLEMENT_REQUIRED", "PERMISSION_DENIED"}:
        return 3
    if status == "RATE_LIMITED":
        return 4
    if status == "DEGRADED":
        return 5
    return 6


if __name__ == "__main__":
    raise SystemExit(main())
