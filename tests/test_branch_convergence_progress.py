import hashlib
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import branch_convergence_progress as target

def mocked(stdout):
    return SimpleNamespace(stdout=stdout)

class BranchSnapshotTests(unittest.TestCase):
    @patch.object(target.subprocess, "run")
    def test_sorted_and_verified(self, run):
        run.return_value = mocked("b"*40+"\trefs/heads/main\n"+"c"*40+"\trefs/heads/core/integration\n")
        refs, manifest, digest = target.remote_refs()
        self.assertEqual(len(refs), 2)
        self.assertEqual(digest, hashlib.sha256(manifest.encode()).hexdigest())
        self.assertTrue(manifest.startswith("c"*40))
    @patch.object(target.subprocess, "run")
    def test_missing_main_fails(self, run):
        run.return_value = mocked("c"*40+"\trefs/heads/core/integration\n")
        with self.assertRaises(ValueError): target.remote_refs()
    @patch.object(target.subprocess, "run")
    def test_duplicate_fails(self, run):
        run.return_value = mocked(("b"*40+"\trefs/heads/main\n")*2+"c"*40+"\trefs/heads/core/integration\n")
        with self.assertRaises(ValueError): target.remote_refs()
    @patch.object(target.subprocess, "run")
    def test_mutating_remote_snapshot_fails_closed(self, run):
        first = "a"*40+"\trefs/heads/main\n"+"b"*40+"\trefs/heads/core/integration\n"
        second = "c"*40+"\trefs/heads/main\n"+"b"*40+"\trefs/heads/core/integration\n"
        run.side_effect = [mocked(first), mocked(second)]
        with self.assertRaises(ValueError): target.remote_refs()

    def test_shared_heads_are_only_identity_aliases(self):
        refs = {"main": "a"*40, "core/integration": "b"*40,
                "legacy": "a"*40, "different": "c"*40}
        groups = target.shared_head_groups(refs)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["branches"], ["legacy", "main"])
        self.assertFalse(groups[0]["retirement_allowed"])
        self.assertEqual(groups[0]["consumer_status"], "UNKNOWN")

    def test_exact_tip_only_and_no_retirement(self):
        refs = {"main": "a"*40, "core/integration": "b"*40,
                "old": "a"*40, "unverified": "c"*40}
        rows = {x["branch"]: x for x in target.classify_exact_tips(refs)}
        self.assertEqual(rows["old"]["exact_tip_matches"], ["main"])
        self.assertEqual(rows["unverified"]["content_disposition"], "UNKNOWN")
        self.assertFalse(any(x["retirement_allowed"] for x in rows.values()))

    @patch.object(target.subprocess, "run")
    def test_invalid_sha_fails(self, run):
        run.return_value = mocked("bad\trefs/heads/main\n"+"c"*40+"\trefs/heads/core/integration\n")
        with self.assertRaises(ValueError): target.remote_refs()

if __name__ == "__main__":
    unittest.main()
