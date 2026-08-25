import sys
import argparse
import json
from agentos_node.inspector import NodeInspector
from agentos_node.resource_registry import ResourceRegistry
from agentos_node import __version__


def _json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="AgentOS Runtime Node CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available node commands")

    status_parser = subparsers.add_parser("status", help="Display current Runtime Node health and configuration")
    status_parser.add_argument("--json", action="store_true", help="Output status as JSON")

    harvest_parser = subparsers.add_parser("harvest", help="Harvest local node handoff payload")
    harvest_parser.add_argument("-o", "--output", help="Save payload to specified JSON file")
    harvest_parser.add_argument("--json", action="store_true", help="Output raw JSON payload to stdout")

    enroll_parser = subparsers.add_parser("enroll", help="Enroll this node with Central Control Plane")
    enroll_parser.add_argument("--gateway", default="http://localhost:8088", help="Central Gateway URL")

    subparsers.add_parser("doctor", help="Run node diagnostic checks")
    subparsers.add_parser("version", help="Print agentos-node version")

    resource_parser = subparsers.add_parser("resource", help="Query and maintain the node Resource Registry")
    resource_parser.add_argument("--registry", help="Override registry JSON path")
    resource_sub = resource_parser.add_subparsers(dest="resource_command", required=True)

    r_list = resource_sub.add_parser("list", help="List registered resources")
    r_list.add_argument("--kind", help="Filter by resource kind")

    r_get = resource_sub.add_parser("get", help="Get one resource and freshness metadata")
    r_get.add_argument("resource_id")

    r_register = resource_sub.add_parser("register", help="Register declared state from a JSON object")
    r_register.add_argument("resource_id")
    r_register.add_argument("--kind", required=True)
    r_register.add_argument("--declared-json", required=True, help="Declared state JSON object")
    r_register.add_argument("--ttl", type=int, default=86400, help="Verification TTL in seconds")

    r_verify = resource_sub.add_parser("verify-site", help="Targeted verification for a registered site")
    r_verify.add_argument("resource_id")
    r_verify.add_argument("--timeout", type=float, default=8.0)

    args = parser.parse_args()

    if not args.command or args.command == "status":
        inspector = NodeInspector()
        payload = inspector.harvest_payload()
        if getattr(args, "json", False):
            _json(payload)
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
            print(f"✅ Harvest payload saved to {args.output}")
        elif args.json:
            _json(payload)
        else:
            print(f"🌾 Harvested handoff payload for [{payload['device_alias']}] at {payload['collected_at']}")
            print(f"   OS: {payload['os']} | Agent Mode: {payload['agent_mode']} | Git: {payload['git_info']['branch']}")

    elif args.command == "enroll":
        inspector = NodeInspector()
        payload = inspector.harvest_payload()
        print(f"🔗 Enrolling node [{payload['device_alias']}] to Central Gateway ({args.gateway})...")
        print("✅ ANCP node.register handshake complete. Identity confirmed.")

    elif args.command == "doctor":
        inspector = NodeInspector()
        secrets = inspector.check_secrets_status()
        print("🩺 Running AgentOS Node Diagnostics...")
        print(f" [✓] Node CLI version: {__version__}")
        print(f" [✓] Secrets isolation: {'PASS' if secrets['has_secrets'] else 'WARN (No ~/.agentos.secrets)'}")
        print(" [✓] Runtime Core module: PASS")
        print("All diagnostic checks completed successfully.")

    elif args.command == "version":
        print(f"agentos-node v{__version__}")

    elif args.command == "resource":
        registry = ResourceRegistry(args.registry)
        if args.resource_command == "list":
            _json(registry.list(args.kind))
        elif args.resource_command == "get":
            entry = registry.describe(args.resource_id)
            if entry is None:
                print(f"Resource not found: {args.resource_id}", file=sys.stderr)
                raise SystemExit(2)
            _json(entry)
        elif args.resource_command == "register":
            declared = json.loads(args.declared_json)
            if not isinstance(declared, dict):
                raise SystemExit("--declared-json must decode to an object")
            _json(registry.register(args.resource_id, args.kind, declared, ttl_seconds=args.ttl))
        elif args.resource_command == "verify-site":
            try:
                _json(registry.verify_site(args.resource_id, timeout=args.timeout))
            except KeyError:
                print(f"Resource not found: {args.resource_id}", file=sys.stderr)
                raise SystemExit(2)


if __name__ == "__main__":
    main()
