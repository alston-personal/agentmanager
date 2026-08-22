#!/usr/bin/env python3
"""Issue a short-lived AgentOS Node Join Reference for development/operator use."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from agent_core.enrollment_store import EnrollmentStore
from runtime_core.onboarding_v1 import BootstrapPolicy


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue a one-time AgentOS Node Join Reference")
    parser.add_argument("--db", required=True, help="Enrollment SQLite database")
    parser.add_argument("--realm-id", required=True)
    parser.add_argument("--core-url", required=True)
    parser.add_argument("--profile", default="edge")
    parser.add_argument("--ttl-minutes", type=int, default=10)
    parser.add_argument("--format", choices=("link", "code", "command"), default="link")
    args = parser.parse_args()

    if args.ttl_minutes < 1 or args.ttl_minutes > 60:
        parser.error("--ttl-minutes must be between 1 and 60")

    expires = datetime.now(timezone.utc) + timedelta(minutes=args.ttl_minutes)
    reference = EnrollmentStore(args.db).issue_reference(
        realm_id=args.realm_id,
        core_url=args.core_url,
        expires_at=expires.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        bootstrap_policy=BootstrapPolicy(profile=args.profile),
    )

    if args.format == "code":
        print(reference.code())
    elif args.format == "command":
        # Shell quoting is intentionally left to the operator/UI because Join
        # References are bearer credentials and should not be copied into logs.
        print("agentos-node enroll --reference '<JOIN_REFERENCE>'")
        print(reference.link())
    else:
        print(reference.link())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
