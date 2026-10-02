from pathlib import Path
import py_compile


def test_runner_pool_ingress_sources_compile():
    py_compile.compile("agent_core/realm_server.py", doraise=True)
    py_compile.compile("agentos_node/bootstrap_control.py", doraise=True)


def test_gateway_exposes_only_typed_scheduler_ingress():
    route = Path("dashboard/app/api/agentos/[...path]/route.ts").read_text(encoding="utf-8")
    assert "/v1/controller/scheduler/submit" in route
    assert "controller\\/scheduler\\/requests" in route
    assert "/v1/controller/dispatch" not in route


def test_https_helper_never_uses_ssh():
    helper = Path("scripts/submit_agentos_scheduler_request_https.sh").read_text(encoding="utf-8")
    assert "curl " in helper
    assert " ssh " not in helper
    assert "scheduler/submit" in helper
