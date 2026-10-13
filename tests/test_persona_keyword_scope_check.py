import io,json,tempfile,unittest
from pathlib import Path
from scripts.persona_keyword_scope_check import check_keyword_scope

class Response:
    def __init__(self,d): self.d=d
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def read(self,n): return json.dumps(self.d).encode()

class ScopeCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/"creds.json"
        self.path.write_text(json.dumps({"bindings":{"galaxy:threads:persona:12345":{
            "platform":"threads","product_id":"galaxy","auth_profile":"persona",
            "username":"mio.milkcat","provider_account_id":"12345","access_token":"TEST_SECRET"}}}))
    def tearDown(self): self.tmp.cleanup()
    def run_case(self,body):
        def opener(req,timeout):
            self.assertEqual(timeout,15)
            self.assertIn("debug_token",req.full_url)
            return Response(body)
        return check_keyword_scope(credentials_path=self.path,opener=opener)
    def test_granted(self):
        x=self.run_case({"data":{"is_valid":True,"scopes":["threads_keyword_search"]}})
        self.assertEqual(x["reason"],"GRANTED")
        self.assertNotIn("TEST_SECRET",str(x))
    def test_missing_scope(self):
        self.assertEqual(self.run_case({"data":{"is_valid":True,"scopes":["threads_basic"]}})["reason"],"NOT_GRANTED")
    def test_uncertain_token_not_pass(self):
        self.assertEqual(self.run_case({"data":{"is_valid":False,"scopes":["threads_keyword_search"]}})["status"],"BLOCKED")
    def test_identity_isolation(self):
        self.path.write_text(json.dumps({"bindings":{"galaxy:threads:persona:12345":{"platform":"threads","product_id":"galaxy","username":"other","provider_account_id":"12345","access_token":"TEST_SECRET"}}}))
        self.assertEqual(check_keyword_scope(credentials_path=self.path)["reason"],"ACCOUNT_BINDING_UNVERIFIED")
    def test_fail_closed_missing_file(self):
        self.path.unlink()
        self.assertEqual(check_keyword_scope(credentials_path=self.path)["reason"],"DIAGNOSTIC_UNAVAILABLE")
