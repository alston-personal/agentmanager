"""Immutable service release must select a dependency-complete Python, not an empty system fallback."""
from pathlib import Path
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts"/"install_systemd_user.sh"

class ImmutablePythonDependencyTest(unittest.TestCase):
    def test_contract(self):
        s=SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"$DATA_ROOT/runtime/python/venv/bin/python3"',s)
        self.assertIn('"$HOME/agentmanager/venv/bin/python3"',s)
        self.assertIn('import google.generativeai, telegram, dotenv, psutil, yaml',s)
        self.assertIn('refusing to replace active service units',s)
        self.assertIn('exit 32',s)
        self.assertIn('AGENTOS_SERVICE_DEPENDENCY_GUARD',s)
        self.assertIn('system_python_unverified',s)
        w=(ROOT/'.github/workflows/oracle-core-bundle-immutable-runtime-convergence.yml').read_text()
        self.assertIn('AGENTOS_SERVICE_DEPENDENCY_GUARD=1',w)
        self.assertIn('agentos_service_python=$PYTHON_PROFILE',s)
        self.assertEqual(subprocess.run(["bash","-n",str(SCRIPT)]).returncode,0)

if __name__=="__main__": unittest.main()
