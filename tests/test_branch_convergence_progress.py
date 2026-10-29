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
    def test_invalid_sha_fails(self, run):
        run.return_value = mocked("bad\trefs/heads/main\n"+"c"*40+"\trefs/heads/core/integration\n")
        with self.assertRaises(ValueError): target.remote_refs()

if __name__ == "__main__":
    unittest.main()
