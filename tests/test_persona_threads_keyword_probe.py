import io
import json
import unittest
from urllib.error import HTTPError
from scripts.persona_threads_keyword_probe import probe

class Response:
    def __init__(self, data):
        self.data = data
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def read(self, n): return json.dumps(self.data).encode()

class KeywordProbeTests(unittest.TestCase):
    def run_probe(self, **extra):
        args = dict(binding_account="mio.milkcat", expected_account="mio.milkcat",
                    allowed_scopes=["threads_keyword_search"], token="fake-secret",
                    query="穿搭", opener=lambda req, timeout: Response({"data": [{"id": "11", "text": "post"}]}))
        args.update(extra)
        return probe(**args)

    def test_valid_probe_never_claims_verified_or_prints_text(self):
        data=self.run_probe()
        self.assertEqual(data["status"], "UNVERIFIED")
        self.assertFalse(data["write_performed"])
        self.assertNotIn("post", str(data.get("items")))
        self.assertNotIn("fake-secret", json.dumps(data))
        self.assertEqual(data["result_count"], 1)

    def test_scope_required_blocks_without_network(self):
        self.assertEqual(self.run_probe(allowed_scopes=[])["reason"], "AUTH_SCOPE_REQUIRED")

    def test_account_isolation(self):
        self.assertEqual(self.run_probe(binding_account="oursong_alstonhuang")["reason"], "ACCOUNT_MISMATCH")

    def test_missing_token_blocks(self):
        self.assertEqual(self.run_probe(token="")["reason"], "TOKEN_UNAVAILABLE")

    def test_no_long_queries(self):
        self.assertEqual(self.run_probe(query="x"*61)["reason"], "INVALID_QUERY")

    def test_http_auth_error_is_classified_without_body(self):
        def fail(req, timeout): raise HTTPError(req.full_url, 403, "forbidden", {}, io.BytesIO(b"SECRET"))
        data=self.run_probe(opener=fail)
        self.assertEqual(data["reason"], "AUTH_OR_SCOPE_DENIED")
        self.assertNotIn("SECRET", json.dumps(data))

    def test_unexpected_response_blocks(self):
        self.assertEqual(self.run_probe(opener=lambda req, timeout: Response({"error":"leak"}))["reason"],
                         "PROVIDER_ERROR")

    def test_exact_bounded_request(self):
        captured=[]
        def open_(req, timeout):
            captured.append(req)
            return Response({"data":[]})
        self.run_probe(opener=open_)
        self.assertEqual(len(captured),1)
        self.assertIn("limit=5",captured[0].full_url)
        self.assertIn("search_type=RECENT",captured[0].full_url)
        self.assertNotIn("fake-secret",captured[0].full_url)
        self.assertEqual(captured[0].get_header("Authorization"), "Bearer fake-secret")


    def test_provider_error_envelope_rejected(self):
        result=self.run_probe(opener=lambda req, timeout: Response({"error":{"message":"sensitive provider data"},"data":[]}))
        self.assertEqual(result["reason"], "PROVIDER_ERROR")
        self.assertNotIn("sensitive", json.dumps(result))

    def test_rate_limit_is_explicit(self):
        def fail(req, timeout): raise HTTPError(req.full_url, 429, "limited", {}, io.BytesIO(b"secret"))
        self.assertEqual(self.run_probe(opener=fail)["reason"], "RATE_LIMITED")

    def test_overlarge_or_malformed_results_rejected(self):
        self.assertEqual(self.run_probe(opener=lambda req, timeout: Response({"data":[{}]*6}))["reason"], "RESULT_SCHEMA_UNEXPECTED")
        self.assertEqual(self.run_probe(opener=lambda req, timeout: Response({"data":[None]}))["reason"], "RESULT_SCHEMA_UNEXPECTED")

    def test_scope_whitespace_is_normalized(self):
        self.assertEqual(self.run_probe(allowed_scopes=[" threads_keyword_search "])["status"], "UNVERIFIED")
