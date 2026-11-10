#!/usr/bin/env python3
"""Retired legacy Layout Lab deployment carrier.

Canonical production publication is now owned by the fixed AgentOS executor path:

  layoutlib.release.materialize
    -> layoutlib.production.promote
    -> layoutlib.production.parity.inspect

This file is intentionally non-operational so historical references fail safely.
"""
from __future__ import annotations


def main() -> int:
    print(
        "RETIRED: deploy_layoutlab_official_v2.py no longer has deployment authority; "
        "use the governed LayoutLib materialize/promote/parity executor path."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
