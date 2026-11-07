import unittest
from datetime import datetime, timezone
from agent_core.hermes_github_scan import evaluate, normalized_repo, run_scan

NOW=datetime(2026,11,7,tzinfo=timezone.utc)

def fixture(name="Example/project",**kwargs):
    return {"full_name":name,"license":{"spdx_id":"MIT"},"pushed_at":"2026-11-06T01:00:00Z",
            "stargazers_count":33,"default_branch":"main", **kwargs}

class HermesGithubScanTests(unittest.TestCase):
    def test_invalid_repository(self):
        for bad in ["../etc","owner/repo/other","foo?x/repo","/repo","owner/"]:
            with self.assertRaises(ValueError):
                normalized_repo(bad)
    def test_duplicate_repo_scanned_once(self):
        calls=[]
        def fetch(repo):
            calls.append(repo)
            return fixture(name=repo)
        report=run_scan(["Example/project","example/PROJECT"],fetch,now=NOW)
        self.assertEqual(report["source_count"],1)
        self.assertEqual(len(calls),1)
        self.assertEqual(report["candidate_count"],1)
        self.assertFalse(report["runtime_receipt"])
    def test_archived_rejected(self):
        self.assertEqual(evaluate("Example/project",fixture(archived=True),now=NOW.isoformat())["classification"],"REJECTED")
    def test_unknown_license_no_adoption(self):
        a=evaluate("Example/project",fixture(license=None),now=NOW.isoformat())
        self.assertEqual(a["classification"],"DESIGN_REFERENCE")
        self.assertFalse(a["adoption_authorized"])
    def test_identity_mismatch_fails_closed(self):
        with self.assertRaises(ValueError):
            evaluate("Example/project",fixture(name="someone/else"),now=NOW.isoformat())
    def test_unchanged_fingerprint_dedup(self):
        first=run_scan(["Example/project"],lambda _:fixture(),now=NOW)
        digest=first["findings"][0]["fingerprint"]
        second=run_scan(["Example/project"],lambda _:fixture(),old_fingerprints={"example/project":digest},now=NOW)
        self.assertEqual(second["changed_count"],0)
    def test_partial_failure_sanitized(self):
        report=run_scan(["Example/project"],lambda _: (_ for _ in ()).throw(RuntimeError("secret-error")),now=NOW)
        self.assertEqual(report["candidate_count"],0)
        self.assertEqual(report["failures"][0]["error_class"],"RuntimeError")
        self.assertNotIn("secret-error",str(report))
    def test_max_repo_limit(self):
        with self.assertRaises(ValueError):
            run_scan(["a/b"]*26,lambda _:fixture(),now=NOW)

if __name__=="__main__":
    unittest.main()
