"""Repository verification must fail closed; no real GitHub or Oracle calls."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from subprocess import CompletedProcess

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "register_project.py"
spec = importlib.util.spec_from_file_location("register_project_under_test", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ProjectRepoGateTests(unittest.TestCase):
    def test_missing_url_is_blocked(self):
        state = mod.verify_project_repository("wow-nav-assist", None)
        self.assertEqual(state["repository_state"], "blocked")

    def test_wrong_owner_is_blocked_before_network(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(mod, "PHYSICAL_PROJECTS_ROOT", Path(td)):
                state = mod.verify_project_repository(
                    "wow-nav-assist", "https://github.com/another-owner/wow-nav-assist"
                )
        self.assertEqual(state["repository_state"], "blocked")
        self.assertEqual(state["blocker"], "repo_url_missing_or_invalid")

    def test_missing_checkout_is_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(mod, "PHYSICAL_PROJECTS_ROOT", Path(td)):
                state = mod.verify_project_repository(
                    "wow-nav-assist", "https://github.com/alston-personal/wow-nav-assist"
                )
        self.assertEqual(state["blocker"], "code_checkout_missing")

    def test_remote_and_local_head_must_agree(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td) / "wow-nav-assist"
            (folder / ".git").mkdir(parents=True)
            sha = "a" * 40
            def git_run(cmd, **kwargs):
                suffix = tuple(cmd[3:])
                mapping = {
                    ("remote", "get-url", "origin"): "https://github.com/alston-personal/wow-nav-assist.git",
                    ("branch", "--show-current"): "main",
                    ("rev-parse", "HEAD"): sha,
                    ("ls-remote", "--heads", "origin", "main"): sha + "\trefs/heads/main",
                }
                return CompletedProcess(cmd, 0, stdout=mapping[suffix], stderr="")
            with patch.object(mod, "PHYSICAL_PROJECTS_ROOT", Path(td)):
                with patch.object(mod.subprocess, "run", side_effect=git_run):
                    state = mod.verify_project_repository(
                        "wow-nav-assist", "https://github.com/alston-personal/wow-nav-assist"
                    )
                    self.assertEqual(state["repository_state"], "provisioned")
                    self.assertEqual(state["source_commit"], sha)
                    def mismatched(cmd, **kwargs):
                        result = git_run(cmd, **kwargs)
                        if tuple(cmd[3:]) == ("rev-parse", "HEAD"):
                            result.stdout = "b" * 40
                        return result
                    with patch.object(mod.subprocess, "run", side_effect=mismatched):
                        state = mod.verify_project_repository(
                            "wow-nav-assist", "https://github.com/alston-personal/wow-nav-assist"
                        )
                        self.assertEqual(state["repository_state"], "blocked")

    def test_metadata_preserves_existing_custom_keys(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "wow-nav-assist" / "project.yaml"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"custom": "keep", "priority": 1}))
            with patch.object(mod, "DATA_PROJECTS_DIR", root):
                with patch.object(mod, "PHYSICAL_PROJECTS_ROOT", root):
                    mod.save_repo_registration("wow-nav-assist", "WoW Nav Assist",
                                               {"repository_state": "blocked", "repo_url": None})
            data = json.loads(path.read_text())
            self.assertEqual(data["custom"], "keep")
            self.assertEqual(data["priority"], 1)
            self.assertEqual(data["repository_state"], "blocked")


if __name__ == "__main__":
    unittest.main()
