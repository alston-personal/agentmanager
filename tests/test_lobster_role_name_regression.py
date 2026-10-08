"""Ensure Lobster task wrapper uses the resolved role_name, not undefined role."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class LobsterRoleNameRegression(unittest.TestCase):
    def test_task_wrapper_does_not_reference_undefined_role(self):
        tree = ast.parse((ROOT / "scripts" / "lobster.py").read_text(encoding="utf-8"))
        wrapper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_claude_task_wrapper")
        names = {n.id for n in ast.walk(wrapper) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        self.assertNotIn("role", names)
        self.assertIn("role_name", names)

if __name__ == "__main__":
    unittest.main()
