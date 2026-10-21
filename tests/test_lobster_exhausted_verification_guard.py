import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_lobster_executor_refuses_exhausted_blocked_verification():
    tree = ast.parse((ROOT / "scripts/lobster.py").read_text())
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
              and node.name == "completion_begin")
    source = ast.get_source_segment((ROOT / "scripts/lobster.py").read_text(), fn)
    assert 'WorkCompletion.classify_blocker(item.get("blocker"))' in source
    assert 'WorkCompletion.VERIFICATION_RETRY_LIMIT' in source
    assert 'retry_count >= verification_budget' in source
    assert 'return None' in source
    assert source.index("retry_count >= verification_budget") < source.index('WorkCompletion.transition(', source.index('elif item["status"] == "blocked"'))
