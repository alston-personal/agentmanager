"""Regression guard: Lobster must never mark unverifiable output as PASS."""
from pathlib import Path
import ast
import unittest


ROOT = Path(__file__).resolve().parents[1]
LOBSTER = ROOT / "scripts" / "lobster.py"


class LobsterInspectorFailClosedTest(unittest.TestCase):
    def test_missing_inspector_does_not_pass(self):
        tree = ast.parse(LOBSTER.read_text(encoding="utf-8"))
        methods = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "run_with_inspector"]
        self.assertEqual(len(methods), 1)
        target = methods[0]
        guards = [
            node for node in ast.walk(target)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Compare)
            and isinstance(node.test.left, ast.Name)
            and node.test.left.id == "Inspector"
            and len(node.test.ops) == 1
            and isinstance(node.test.ops[0], ast.Is)
            and len(node.test.comparators) == 1
            and isinstance(node.test.comparators[0], ast.Constant)
            and node.test.comparators[0].value is None
        ]
        self.assertEqual(len(guards), 1)
        outputs = [node for node in ast.walk(guards[0]) if isinstance(node, ast.Return)]
        self.assertEqual(len(outputs), 1)
        returned = outputs[0].value
        self.assertIsInstance(returned, ast.Tuple)
        self.assertIs(returned.elts[0].value, False)
        self.assertIn("BLOCKED: inspector_unavailable", returned.elts[1].value)


if __name__ == "__main__":
    unittest.main()
