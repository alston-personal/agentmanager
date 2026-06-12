import argparse
import json
import socket
import sys
from pathlib import Path

DATA_ROOT = Path("/home/ubuntu/agent-data")
REGISTRY_FILE = DATA_ROOT / "config" / "port_registry.json"

def is_port_in_use(port: int) -> bool:
    """Check if a port is physically bound by the OS."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

def load_registry() -> dict:
    if not REGISTRY_FILE.exists():
        return {}
    try:
        with open(REGISTRY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading registry: {e}", file=sys.stderr)
        return {}

def save_registry(registry: dict):
    REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REGISTRY_FILE, 'w', encoding='utf-8') as f:
        json.dump(registry, f, indent=2)

def register_port(port: int, project: str, description: str = ""):
    registry = load_registry()
    port_str = str(port)
    if port_str in registry and registry[port_str]['project'] != project:
        print(f"Warning: Port {port} is already registered to {registry[port_str]['project']}.")
    
    registry[port_str] = {
        "project": project,
        "description": description
    }
    save_registry(registry)
    print(f"Successfully registered Port {port} for project '{project}'.")

def allocate_port(project: str, description: str = "", start_port: int = 3000, end_port: int = 8999):
    registry = load_registry()
    
    # Check if project already has a port
    for p_str, info in registry.items():
        if info['project'] == project:
            print(f"Project '{project}' already has port {p_str} allocated.")
            return int(p_str)

    # Find free port
    for p in range(start_port, end_port + 1):
        if str(p) not in registry and not is_port_in_use(p):
            register_port(p, project, description)
            return p
            
    print(f"Error: No free ports available in range {start_port}-{end_port}.")
    sys.exit(1)

def list_ports():
    registry = load_registry()
    if not registry:
        print("Port Registry is empty.")
        return
        
    print(f"{'PORT':<8} | {'PROJECT':<30} | {'DESCRIPTION'}")
    print("-" * 60)
    for port in sorted(registry.keys(), key=lambda x: int(x)):
        info = registry[port]
        print(f"{port:<8} | {info['project']:<30} | {info.get('description', '')}")

def free_port(port: int):
    registry = load_registry()
    port_str = str(port)
    if port_str in registry:
        project = registry[port_str]['project']
        del registry[port_str]
        save_registry(registry)
        print(f"Port {port} (was {project}) has been freed.")
    else:
        print(f"Port {port} is not in the registry.")

def main():
    parser = argparse.ArgumentParser(description="AgentOS Port Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    alloc_parser = subparsers.add_parser("allocate", help="Allocate a free port for a project")
    alloc_parser.add_argument("project", help="Name of the project")
    alloc_parser.add_argument("--desc", default="", help="Description of the service")
    alloc_parser.add_argument("--start", type=int, default=3000, help="Start range")
    alloc_parser.add_argument("--end", type=int, default=8999, help="End range")

    reg_parser = subparsers.add_parser("register", help="Manually register a port")
    reg_parser.add_argument("port", type=int, help="Port number")
    reg_parser.add_argument("project", help="Name of the project")
    reg_parser.add_argument("--desc", default="", help="Description")

    list_parser = subparsers.add_parser("list", help="List all registered ports")

    free_parser = subparsers.add_parser("free", help="Free a port")
    free_parser.add_argument("port", type=int, help="Port number to free")

    args = parser.parse_args()

    if args.command == "allocate":
        allocate_port(args.project, args.desc, args.start, args.end)
    elif args.command == "register":
        register_port(args.port, args.project, args.desc)
    elif args.command == "list":
        list_ports()
    elif args.command == "free":
        free_port(args.port)

if __name__ == "__main__":
    main()
