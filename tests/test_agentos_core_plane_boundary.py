import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CRITICAL_RUNTIME_FILES = [
    ROOT / "agentos_client" / "client.py",
    ROOT / "agent_core" / "distributed_gateway.py",
    ROOT / "agent_core" / "distributed_control_plane.py",
    ROOT / "agent_core" / "context_compiler.py",
    ROOT / "agentos_node" / "remote_worker.py",
    ROOT / "scripts" / "agentos_node_daemon.py",
]
FORBIDDEN_MARKERS = (
    "GITHUB_TOKEN",
    "api.github.com",
    ".github/workflows",
    "workflow_dispatch",
    "actions/checkout",
)


def test_core_v01_plane_contract_separates_execution_from_ci():
    contract = json.loads((ROOT / ".agentos" / "core-v01-plane-contract.json").read_text(encoding="utf-8"))
    assert contract["schema"] == "agentos.core-plane-contract/v0.1"
    execution = contract["execution_plane"]
    assert "agentos-control-plane.service" in execution["required_services"]
    assert "agentos-node.service" in execution["required_services"]
    assert "GitHub Actions runner" in execution["forbidden_runtime_dependencies"]
    assert "normal AgentOS task executor" in contract["ci_deploy_plane"]["not_roles"]


def test_runtime_critical_path_has_no_github_actions_transport_dependency():
    missing = [str(path.relative_to(ROOT)) for path in CRITICAL_RUNTIME_FILES if not path.exists()]
    assert not missing, f"runtime contract files missing: {missing}"
    violations = []
    for path in CRITICAL_RUNTIME_FILES:
        text = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_MARKERS:
            if marker in text:
                violations.append(f"{path.relative_to(ROOT)} contains {marker}")
    assert not violations, "GitHub leaked into execution critical path: " + "; ".join(violations)
