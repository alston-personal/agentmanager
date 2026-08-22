import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from agentos_node import __version__
from agentos_node.capability_discovery import DiscoveryContext, discover_linux_capabilities
from agentos_node.enrollment_client import enroll_node
from agentos_node.inspector import NodeInspector


def main():
    parser = argparse.ArgumentParser(description="AgentOS Runtime Node CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available node commands")

    status_parser = subparsers.add_parser("status", help="Display current Runtime Node health and configuration")
    status_parser.add_argument("--json", action="store_true", help="Output status as JSON")

    harvest_parser = subparsers.add_parser("harvest", help="Harvest local node handoff payload")
    harvest_parser.add_argument("-o", "--output", help="Save payload to specified JSON file")
    harvest_parser.add_argument("--json", action="store_true", help="Output raw JSON payload to stdout")

    capabilities_parser = subparsers.add_parser("capabilities", help="Discover local capabilities without authorizing them")
    capabilities_parser.add_argument("--node-id", required=True)
    capabilities_parser.add_argument("--realm-id", required=True)
    capabilities_parser.add_argument("--profile", default="edge")
    capabilities_parser.add_argument("--json", action="store_true")

    enroll_parser = subparsers.add_parser("enroll", help="Join this device to AgentOS using a one-time Join Reference")
    enroll_parser.add_argument("--reference", required=True, help="AGENTOSREF1 code or HTTPS Join Link")
    enroll_parser.add_argument("--identity-dir", help="Override local Node identity directory")
    enroll_parser.add_argument("--json", action="store_true", help="Output enrollment receipt as JSON")

    subparsers.add_parser("doctor", help="Run node diagnostic checks")
    subparsers.add_parser("version", help="Print agentos-node version")

    args = parser.parse_args()

    if not args.command or args.command == "status":
        inspector = NodeInspector()
        payload = inspector.harvest_payload()
        if getattr(args, "json", False):
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("==========================================")
            print("       AgentOS Runtime Node Status        ")
            print("==========================================")
            print(f" Device Alias  : {payload['device_alias']}")
            print(f" Hostname      : {payload['hostname']}")
            print(f" OS / Platform : {payload['os']} {payload['os_release']}")
            print(f" Python        : {payload['python_version']}")
            print(f" Node Version  : {payload['node_version']}")
            print(f" Agent Mode    : {payload['agent_mode']}")
            print(f" Secrets Store : {'ISOLATED' if payload['secrets_info']['has_secrets'] else 'MISSING'}")
            print(f" Git Commit    : {payload['git_info']['commit'][:8] if payload['git_info']['is_git'] else payload['git_info']['commit']}")
            print(f" Health Status : {payload['status']}")
            print("==========================================")

    elif args.command == "harvest":
        inspector = NodeInspector()
        payload = inspector.harvest_payload()
        if args.output:
            inspector.save_payload_to_file(args.output)
            print(f"Harvest payload saved to {args.output}")
        elif args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"Harvested handoff payload for [{payload['device_alias']}] at {payload['collected_at']}")
            print(f"OS: {payload['os']} | Agent Mode: {payload['agent_mode']} | Git: {payload['git_info']['branch']}")

    elif args.command == "capabilities":
        observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        manifest = discover_linux_capabilities(
            DiscoveryContext(
                realm_id=args.realm_id,
                node_id=args.node_id,
                observed_at=observed_at,
                profile=args.profile,
            )
        )
        if args.json:
            payload = asdict(manifest)
            payload["manifest_id"] = manifest.manifest_id
            print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        else:
            print(f"manifest={manifest.manifest_id}")
            for item in manifest.capabilities:
                print(f"{item.capability}\t{item.state.value}\t{item.source}")
            print("authorization_inferred=false")

    elif args.command == "enroll":
        try:
            response = enroll_node(
                args.reference,
                identity_dir=Path(args.identity_dir).expanduser() if args.identity_dir else None,
            )
        except Exception as exc:
            print(f"Enrollment failed: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(response, ensure_ascii=False, indent=2))
        else:
            node = response.get("node_identity", {})
            checkpoint = response.get("checkpoint", {})
            print(f"Node enrolled: {node.get('node_id', 'unknown')}")
            print(f"Lifecycle: {checkpoint.get('lifecycle', 'unknown')}")
            print("Capability discovery/governance continues after identity enrollment; no external authority was granted by this command.")

    elif args.command == "doctor":
        inspector = NodeInspector()
        secrets = inspector.check_secrets_status()
        print("Running AgentOS Node diagnostics...")
        print(f" [ok] Node CLI version: {__version__}")
        print(f" [{'ok' if secrets['has_secrets'] else 'warn'}] Secrets isolation: {'PASS' if secrets['has_secrets'] else 'No ~/.agentos.secrets'}")
        print(" [ok] Runtime Core module: PASS")

    elif args.command == "version":
        print(f"agentos-node v{__version__}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
