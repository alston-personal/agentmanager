import ast
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
class LocalExecutorRuntimeTest(unittest.TestCase):
    def test_no_mutable_port_checker_path(self):
        source=(ROOT / "scripts/lobster.py").read_text(encoding="utf-8")
        self.assertNotIn('/home/ubuntu/agentmanager/scripts/local_port_checker.py',source)
        self.assertIn('Path(__file__).resolve().parent / "local_port_checker.py"',source)
        ast.parse(source)
if __name__=="__main__": unittest.main()
