from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_realm_node_transactional_ota_user.sh"


class OTARemoteScriptIntegrityTests(unittest.TestCase):
    def test_shell_syntax_and_embedded_python_compile(self):
        script = SCRIPT.read_text(encoding="utf-8")
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
        blocks = re.findall(r"^[ \t]*python3 - <<'PY'\n(.*?)^PY$", script, re.MULTILINE | re.DOTALL)
        self.assertEqual(len(blocks), 4)
        for index, code in enumerate(blocks):
            with self.subTest(block=index):
                compile(code, str(SCRIPT), "exec")

    def test_both_ota_entry_scripts_pin_local_git_object_hash(self):
        script = SCRIPT.read_text(encoding="utf-8")
        for file_name, variable in (
            ("transactional_ota.ps1", "STAGE_SCRIPT_SHA256"),
            ("transactional_ota_finalize.ps1", "FINALIZE_SCRIPT_SHA256"),
        ):
            with self.subTest(file_name=file_name):
                self.assertIn("git cat-file -e", script)
                self.assertIn('git show "${TOOL_COMMIT}:scripts/windows/' + file_name + '"', script)
                self.assertIn(variable + '="$(git show', script)
                self.assertIn('os.environ["' + variable + '"]', script)

    def test_all_three_remote_executions_require_hash_before_invocation(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertEqual(source.count("Invoke-WebRequest -UseBasicParsing"), 3)
        self.assertEqual(source.count("Get-FileHash -Algorithm SHA256 -LiteralPath $p"), 3)
        self.assertEqual(source.count("ota finalize hash mismatch"), 2)
        self.assertEqual(source.count("ota stage hash mismatch"), 1)
        self.assertIn("throw 'ota finalize hash mismatch'", source)
        self.assertIn("throw 'ota stage hash mismatch'", source)



    def test_accept_finalizer_requires_same_candidate_commit(self):
        finalizer = (SCRIPT.parent / "windows/transactional_ota_finalize.ps1").read_text(
            encoding="utf-8"
        )
        wrapper = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("[string]$ExpectedCommit", finalizer)
        self.assertIn("$current.source_commit -cne $ExpectedCommit", finalizer)
        self.assertIn("expected immutable candidate commit required", finalizer)
        self.assertIn("candidate commit changed before finalize acceptance", finalizer)
        self.assertIn("-Action accept -ExpectedCommit", wrapper)
        self.assertNotIn("-Action rollback -ExpectedCommit", wrapper)

if __name__ == "__main__":
    unittest.main()
