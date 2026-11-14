"""One-shot WoW read-only Node-presence Bridge, candidate only.

Consumes 200 RGB cells from a trusted local capture caller via stdin. An
enrolled AgentOS Node must successfully complete a *fresh authenticated ONE
heartbeat* before the pre-installed reply slot is touched. This is Node
presence only, NOT the Runtime task reader, chat, or a resident service.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from agentos_node.wow_bridge_protocol import NodeBoundStatusGateway
from agentos_node.wow_control_adapter import WoWControlAdapter
from agentos_node.wow_slot_publisher import publish_status_reply


def process_probe(cells: list[int], *, config_path: Path, policy_path: Path,
                  slot_dir: Path, node_factory=None) -> dict:
    """Read-only status, no game-asserted identity, no account or shell actions."""
    if node_factory is None:
        from agentos_node.client_cli import _load_policy
        from agentos_node.thin_client_transport import ClientConfig, build_client
        def node_factory():
            config = ClientConfig.load(config_path)
            transport = build_client(config, _load_policy(policy_path))
            return transport

    def fresh_one_probe() -> bool:
        try:
            transport = node_factory()
            result = transport.heartbeat()
            # The server, not Lua or a locally written heartbeat lease, must
            # acknowledge the authenticated heartbeat.
            return (isinstance(result, dict) and
                    result.get("heartbeat_recorded") is True)
        except Exception:
            return False

    # This snapshot describes *only* the current Node heartbeat. Never
    # invent a Paw state or a canonical ONE Receipt.
    adapter = WoWControlAdapter(lambda: {"state": "NODE_ONLINE",
                                         "paw": "unverified", "receipt": None})
    gateway = NodeBoundStatusGateway(fresh_one_probe, adapter.execute)
    return publish_status_reply(cells, gateway, slot_dir)


def main() -> int:
    # The launcher must supply the exact installed Node and AddOn locations.
    # This CLI intentionally cannot enroll a Node, select a Realm or install.
    if len(sys.argv) != 4:
        print('{"status":"UNAVAILABLE","reason":"TRUSTED_HOST_PATHS_REQUIRED"}')
        return 2
    try:
        cells = json.loads(sys.stdin.read(4096))
        result = process_probe(cells, config_path=Path(sys.argv[1]),
                               policy_path=Path(sys.argv[2]),
                               slot_dir=Path(sys.argv[3]))
    except Exception:
        print('{"status":"UNAVAILABLE","reason":"BRIDGE_UNVERIFIED"}')
        return 2
    # No credentials, raw game session, or internal host paths are reported.
    print(json.dumps(result, separators=(",", ":")))
    return 0 if result.get("status") == "PUBLISHED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
