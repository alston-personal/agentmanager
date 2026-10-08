"""No dry-run or skipped Inspector verdict may count as verified work."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / "scripts" / "lobster.py"

class LobsterVerificationTruthfulness(unittest.TestCase):
    def test_dry_run_and_skip_cannot_return_success(self):
        tree=ast.parse(ROOT.read_text(encoding="utf-8"))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="run_with_inspector")
        for node in ast.walk(fn):
            if isinstance(node,ast.Return) and isinstance(node.value,ast.Tuple):
                vals=node.value.elts
                if len(vals)==2 and isinstance(vals[1],ast.JoinedStr):
                    rendered="".join(x.value for x in vals[1].values if isinstance(x,ast.Constant))
                    if rendered.startswith("SKIP:"):
                        self.assertIsInstance(vals[0],ast.Constant)
                        self.assertIs(vals[0].value,False)
                if len(vals)==2 and isinstance(vals[1],ast.Constant) and "dry_run" in str(vals[1].value):
                    self.assertIs(vals[0].value,False)

if __name__=="__main__":
    unittest.main()
