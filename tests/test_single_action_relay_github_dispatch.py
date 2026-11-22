"""Prevent recovered legacy code from shadowing the governed Actions dispatcher."""
import ast
from pathlib import Path

from agentos_node import action_relay


def test_only_one_github_dispatcher_definition_is_executable():
    source = Path(action_relay.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    definitions = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_github_actions_dispatch"
    ]
    assert len(definitions) == 1
    assert action_relay.ACTIONS["github.actions.workflow.dispatch"] is action_relay._github_actions_dispatch


def test_effective_dispatcher_has_exact_main_sha_and_teams_only_guard():
    import inspect
    source = inspect.getsource(action_relay._github_actions_dispatch)
    assert '"oracle-core-bundle-immutable-runtime-convergence.yml", "main"' in source
    assert '"expected_main_sha": expected_head_sha' in source
    assert '"teams_only": "true"' in source
    assert "protected main head differs from approved source commit" in source
