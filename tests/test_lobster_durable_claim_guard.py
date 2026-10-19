"""Keep durable Lobster work fenced before executor invocation."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "lobster.py"


def test_durable_work_execution_is_claim_gated():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    functions = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    begin = ast.unparse(functions["completion_begin"])
    main = ast.unparse(functions["main"])
    assert "work_item_not_owned_by_lobster" in begin
    assert "work_item_already_in_progress" in begin
    assert "work_item_not_runnable" in begin
    assert "work_item_not_found" in begin
    claim = main.index("work_id = completion_begin(task['text'])")
    guard = main.index("if durable_id and work_id != durable_id:")
    executor = main.index("run_with_inspector(")
    assert claim < guard < executor
    assert "if '[WI:' in task['text']" in main


def test_completion_begin_behavioral_claim_fencing():
    """Execute the real extracted function against deterministic Ledger doubles."""
    from unittest.mock import Mock
    from typing import Optional
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "completion_begin")
    code = compile(ast.Module(body=[fn], type_ignores=[]), str(SOURCE), "exec")
    item = {"owner": "role://lobster", "status": "accepted", "next_action": "safe inspect"}
    api = Mock()
    api.item_id_from_task.return_value = "a"
    api.load.return_value = {"items": {"a": item}}
    api.transition.return_value = {"status": "in_progress"}
    ns = {"WorkCompletion": api, "COMPLETION_STATE": Path("/tmp/test-only-work-items.json"),
          "logger": Mock(), "Optional": Optional}
    exec(code, ns)
    begin = ns["completion_begin"]

    assert begin("[WI:a] safe inspect") == "a"
    assert api.transition.call_count == 1

    for status, owner in [
        ("in_progress", "role://lobster"),
        ("blocked", "role://lobster"),
        ("accepted", "role://foreign"),
    ]:
        api.transition.reset_mock()
        item.update(status=status, owner=owner)
        assert begin("[WI:a] safe inspect") is None
        api.transition.assert_not_called()

    api.load.return_value = {"items": {}}
    assert begin("[WI:a] missing") is None
    api.transition.assert_not_called()


def test_real_ledger_claim_is_single_winner_and_owner_fenced():
    """Two competing claim attempts must not both transition accepted -> running."""
    import importlib.util
    import sys
    import tempfile
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    spec = importlib.util.spec_from_file_location("work_completion_guard_test", ROOT / "scripts" / "work_completion.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as td:
        ledger = Path(td) / "items.json"
        module.register(ledger, work_id="race", project_id="test", title="Claim race",
                        owner="role://lobster", next_action="read-only probe",
                        acceptance=["one winner"])
        start = Barrier(2)
        def attempt():
            start.wait()
            try:
                module.transition(ledger, work_id="race", target="in_progress",
                                  actor="role://lobster", expected_owner="role://lobster")
                return "won"
            except ValueError:
                return "lost"
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(attempt) for _ in range(2)]
            results = [f.result(timeout=10) for f in futures]
        assert sorted(results) == ["lost", "won"]
        assert module.load(ledger)["items"]["race"]["status"] == "in_progress"

        # Simulate an existing owner handoff before an attempted stale claim.
        ledger2 = Path(td) / "foreign.json"
        module.register(ledger2, work_id="foreign", project_id="test", title="Foreign",
                        owner="role://another", next_action="read-only probe",
                        acceptance=["fenced"])
        import pytest
        with pytest.raises(PermissionError, match="work_item_owner_changed"):
            module.transition(ledger2, work_id="foreign", target="in_progress",
                              actor="role://lobster", expected_owner="role://lobster")
        assert module.load(ledger2)["items"]["foreign"]["status"] == "accepted"
