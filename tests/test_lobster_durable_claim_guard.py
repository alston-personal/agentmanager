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
