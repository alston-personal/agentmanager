"""Regression: restored Mio login probe must remain account-bound and read-only."""
import unittest
from pathlib import Path

class MioLegacyIdentityRecoveryTest(unittest.TestCase):
    def test_account_bound_and_no_secret_reads(self):
        source=Path("scripts/probe_threads_web_dm_login_user.sh").read_text(encoding="utf-8")
        self.assertIn("http://127.0.0.1:9224",source)
        self.assertIn("https://www.threads.com/messages",source)
        self.assertIn("threads_web_dm_login_account_state=",source)
        self.assertIn("threads_web_dm_login_session_state=",source)
        self.assertIn("/json/close/",source)
        for unsafe in ("document.cookie","localStorage.getItem","sendMessage(","textarea.value"):
            self.assertNotIn(unsafe,source)
    def test_existing_oracle_workflow_executes_recovered_probe(self):
        workflow=Path(".github/workflows/mio-gui-live-home-diagnostic.yml").read_text(encoding="utf-8")
        self.assertIn("scripts/probe_threads_web_dm_login_user.sh",workflow)
        self.assertIn("bash '$REMOTE'",workflow)

if __name__=="__main__": unittest.main()
