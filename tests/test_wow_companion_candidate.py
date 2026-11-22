import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.wow_companion_candidate as candidate
from scripts.wow_companion_package import BundleError


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "git-source"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "Test"], check=True)
        for addon, lua in (("AgentOSWoW", "AgentOSWoW.lua"), ("AgentOSWoW_R001", "Reply.lua")):
            directory = self.repo / "integrations" / "wow" / addon
            directory.mkdir(parents=True)
            (directory / f"{addon}.toc").write_text(f"## Interface: 16001\n{lua}\n", encoding="utf-8")
            (directory / lua).write_text("print('source')\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-q", "-m", "fixture"], check=True)
        self.sha = subprocess.check_output(["git", "-C", str(self.repo), "rev-parse", "HEAD"], text=True).strip()
        self.stage = self.root / "stage"
        self.output = self.root / "candidate.zip"
        self.patcher = patch.object(candidate, "ROOT", self.repo)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_actual_tracked_candidate_and_status_flags(self):
        result = candidate.build_candidate(self.output, self.stage, self.sha)
        self.assertTrue(self.output.exists())
        self.assertEqual(result["addon_folders"], ["AgentOSWoW", "AgentOSWoW_R001"])
        self.assertFalse(result["complete_companion_suite"])
        self.assertFalse(result["nav_assist_included"])
        self.assertFalse(result["game_client_accepted"])
        self.assertFalse(result["release_approved"])
        lock = json.loads((self.stage / "source-lock.json").read_text())
        self.assertEqual(len(lock["files"]), 4)

    def test_refuses_wrong_source_commit(self):
        with self.assertRaisesRegex(BundleError, "exact source commit"):
            candidate.build_candidate(self.output, self.stage, "0" * 40)
        self.assertFalse(self.output.exists())

    def test_refuses_local_edits_not_in_commit(self):
        path = self.repo / "integrations/wow/AgentOSWoW/AgentOSWoW.lua"
        path.write_text("print('modified')\n", encoding="utf-8")
        with self.assertRaisesRegex(BundleError, "not identical to pinned git commit"):
            candidate.build_candidate(self.output, self.stage, self.sha)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
