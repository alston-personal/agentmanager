import argparse
import json
import os
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

# This allocator is also the canonical port source for persistent project web services.
DATA_ROOT = Path(os.environ.get("AGENT_DATA_ROOT", "/home/ubuntu/agent-data"))
REGISTRY_FILE = DATA_ROOT / "config" / "port_registry.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_port_in_use(port: int) -> bool:
    """Check if a port is physically bound by the OS."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def load_registry() -> dict:
    if not REGISTRY_FILE.exists():
        return {}
    try:
        with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("registry root must be an object")
            return data
    except Exception as e:
        print(f"Error loading registry: {e}", file=sys.stderr)
        raise


def save_registry(registry: dict):
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = REGISTRY_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(registry, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(REGISTRY_FILE)


def register_port(port: int, project: str, description: str = "", *, force: bool = False):
    registry = load_registry()
    port_str = str(port)
    current = registry.get(port_str)
    if current and current.get("project") != project and not force:
        raise RuntimeError(
            f"Port {port} is already governed by project '{current.get('project')}'. "
            "Use the existing owner or explicitly --force after governance approval."
        )

    registry[port_str] = {
        "project": project,
        "description": description,
        "managed_by": "manager://port",
        "updated_at": _now(),
    }
    save_registry(registry)
    print(f"Successfully registered Port {port} for project '{project}'.")
    return port


def allocate_port(project: str, description: str = "", start_port: int = 3000, end_port: int = 8999):
    registry = load_registry()

    # Idempotency: one existing governed allocation is reused.
    existing = [int(p) for p, info in registry.items() if info.get("project") == project]
    if existing:
        port = sorted(existing)[0]
        print(f"Project '{project}' already has port {port} allocated.")
        return port

    for p in range(start_port, end_port + 1):
        if str(p) not in registry and not is_port_in_use(p):
            return register_port(p, project, description)

    raise RuntimeError(f"No free ports available in range {start_port}-{end_port}.")


def list_ports(*, json_output: bool = False):
    registry = load_registry()
    if json_output:
        print(json.dumps(registry, ensure_ascii=False, indent=2))
        return
    if not registry:
        print("Port Registry is empty.")
        return

    print(f"{'PORT':<8} | {'PROJECT':<30} | {'DESCRIPTION'}")
    print("-" * 72)
    for port in sorted(registry.keys(), key=lambda x: int(x)):
        info = registry[port]
        print(f"{port:<8} | {info.get('project',''):<30} | {info.get('description', '')}")


def free_port(port: int, *, project: str | None = None):
    registry = load_registry()
    port_str = str(port)
    if port_str not in registry:
        print(f"Port {port} is not in the registry.")
        return False
    current = registry[port_str]
    if project and current.get("project") != project:
        raise RuntimeError(f"Port {port} belongs to {current.get('project')}, not {project}")
    owner = current.get("project")
    del registry[port_str]
    save_registry(registry)
    print(f"Port {port} (was {owner}) has been freed.")
    return True


def main():
    parser = argparse.ArgumentParser(description="AgentOS Port Manager (authoritative network port allocator)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    alloc_parser = subparsers.add_parser("allocate", help="Allocate or reuse a governed port for a project")
    alloc_parser.add_argument("project")
    alloc_parser.add_argument("--desc", default="")
    alloc_parser.add_argument("--start", type=int, default=3000)
    alloc_parser.add_argument("--end", type=int, default=8999)

    reg_parser = subparsers.add_parser("register", help="Register an explicit port")
    reg_parser.add_argument("port", type=int)
    reg_parser.add_argument("project")
    reg_parser.add_argument("--desc", default="")
    reg_parser.add_argument("--force", action="store_true", help="Override another owner only after governance approval")

    list_parser = subparsers.add_parser("list", help="List governed ports")
    list_parser.add_argument("--json", action="store_true")

    free_parser = subparsers.add_parser("free", help="Free a governed port")
    free_parser.add_argument("port", type=int)
    free_parser.add_argument("--project", help="Require matching current project owner")

    args = parser.parse_args()
    try:
        if args.command == "allocate":
            allocate_port(args.project, args.desc, args.start, args.end)
        elif args.command == "register":
            register_port(args.port, args.project, args.desc, force=args.force)
        elif args.command == "list":
            list_ports(json_output=args.json)
        elif args.command == "free":
            free_port(args.port, project=args.project)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
