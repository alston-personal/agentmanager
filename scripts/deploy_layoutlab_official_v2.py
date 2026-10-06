#!/usr/bin/env python3
"""Retired legacy Layout Lab deployment helper.

Canonical production publication is now handled by the fixed AgentOS executor path:
layoutlib.release.materialize -> layoutlib.production.promote ->
layoutlib.production.parity.inspect.
"""


def main() -> int:
    print(
        "RETIRED: deploy_layoutlab_official_v2.py no longer has deployment authority; "
        "use the governed LayoutLib executor path."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
