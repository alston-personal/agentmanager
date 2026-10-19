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
