"""Lobster Claude executor must use noninteractive CLI mode."""
import ast
from pathlib import Path
import unittest

class LobsterHeadlessClaudeTest(unittest.TestCase):
    def test_wrapper_contains_print_flag(self):
        source=(Path(__file__).resolve().parents[1]/"scripts/lobster.py").read_text(encoding="utf-8")
        tree=ast.parse(source)
        wrapper=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="run_claude_task_wrapper")
        literals=[node.value for node in ast.walk(wrapper) if isinstance(node,ast.Constant) and isinstance(node.value,str)]
        self.assertIn("--print",literals)
        self.assertIn("--output-format",literals)

if __name__=="__main__":
    unittest.main()
