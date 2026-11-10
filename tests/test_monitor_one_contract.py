from pathlib import Path

def test_monitor_one_contract_is_bounded():
    text=Path("agent_core/realm_server.py").read_text(encoding="utf-8")
    for method in (
        "monitor.register","monitor.update","monitor.pause","monitor.resume",
        "monitor.run","monitor.inspect","monitor.list","monitor.delete","monitor.triggered"
    ):
        assert method in text
    block=text.split("def _monitor_command",1)[1].split("def _send",1)[0]
    for forbidden in ("subprocess","shell","executable","filesystem_path"):
        assert forbidden not in block

def test_monitor_gateway_route_is_allowlisted():
    text=Path("dashboard/app/api/agentos/[...path]/route.ts").read_text(encoding="utf-8")
    assert '"/v1/monitor"' in text
