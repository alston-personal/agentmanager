"""Protect canonical Windows Node bootstrap source while retaining explicit compatibility paths."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WindowsBootstrapMainlineContract(unittest.TestCase):
    def test_bootstrap_defaults_to_main(self):
        script = (ROOT / "scripts/bootstrap_clean_windows_node.ps1").read_text(encoding="utf-8")
        self.assertRegex(script, r'\[string\]\$SourceRef\s*=\s*"main"')
        self.assertIn("if ($SourceRef -eq 'core/integration') { $SourceRef = 'main' }", script)
        self.assertIn("$SourceRef = 'main'", script)
        self.assertIn("agentos_bootstrap_source_commit=$sha", script)
        self.assertIn("agentos_source_commit=$sha", script)

    def test_downstream_installer_defaults_to_main(self):
        script = (ROOT / "scripts/install_thin_client_windows.ps1").read_text(encoding="utf-8")
        self.assertRegex(script, r'\[string\]\$SourceRef\s*=\s*"main"')


if __name__ == "__main__":
    unittest.main()
