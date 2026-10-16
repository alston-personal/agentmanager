import unittest
from agent_core.bounty_probe_executor import run_leased_probe

class BountyProbeExecutorTests(unittest.TestCase):
    def test_unleased_refused(self):
        with self.assertRaises(ValueError):
            run_leased_probe(None, {"status":"submitted","capability":"github.repo.read"})

    def test_write_capability_refused(self):
        with self.assertRaises(ValueError):
            run_leased_probe(None, {"status":"leased","capability":"github.pr.write"})

if __name__ == "__main__":
    unittest.main()
