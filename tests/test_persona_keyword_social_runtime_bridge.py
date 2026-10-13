import unittest
from scripts.persona_keyword_social_runtime_bridge import diagnose_keyword_runtime


class SocialKeywordBridgeTests(unittest.TestCase):
    def setUp(self):
        self.base={"binding_id":"galaxy:threads:persona:12345",
                   "provider_account_id":"12345","binding_username":"mio.milkcat","search_term":"散步"}
    def make(self, rows=None, **override):
        receipt={"ok":True,"schema":"agentos.social-receipt/v1",
                 "operation":"keyword.search","platform":"threads",
                 "account_binding_id":self.base["binding_id"],
                 "target_account_id":"12345","receipt_id":"proof",
                 "result":{"items":rows if rows is not None else [{"id":"99","username":"other","text":"散步"}]}}
        receipt.update(override)
        return diagnose_keyword_runtime(**self.base, read_status=lambda req:(200, receipt))
    def test_external_results_remain_unverified(self):
        d=self.make()
        self.assertEqual(d["reason"],"EXTERNAL_POST_PROVENANCE_REQUIRED")
        self.assertEqual(d["items"],[])
        self.assertFalse(d["write_performed"])
    def test_own_only_is_not_external_discovery(self):
        self.assertEqual(self.make(rows=[{"username":"mio.milkcat"}])["reason"],"OWN_POSTS_ONLY")
    def test_missing_binding_denied_before_network(self):
        called=[]
        d=diagnose_keyword_runtime(**{**self.base,"binding_username":"oursong_alstonhuang"},
                                   read_status=lambda req:called.append(req))
        self.assertEqual(d["reason"],"ACCOUNT_BINDING_UNVERIFIED")
        self.assertEqual(called,[])
    def test_identity_mismatch_denied(self):
        self.assertEqual(self.make(target_account_id="999")["reason"],"RECEIPT_IDENTITY_MISMATCH")
    def test_scope_error_classified(self):
        self.assertEqual(self.make(ok=False,error_code="OAuth scope missing")["reason"],"AUTH_SCOPE_REQUIRED")
    def test_too_many_items_rejected(self):
        self.assertEqual(self.make(rows=[{}]*11)["reason"],"RESULT_BOUNDS_INVALID")
    def test_runtime_unavailable_blocks(self):
        def fail(req): raise TimeoutError("timeout")
        self.assertEqual(diagnose_keyword_runtime(**self.base,read_status=fail)["reason"],"SOCIAL_RUNTIME_UNAVAILABLE")
    def test_request_is_bounded_and_read_only(self):
        called=[]
        def status(req):
            called.append(req)
            return 200,{"ok":False,"error_code":"denied"}
        diagnose_keyword_runtime(**self.base,read_status=status)
        self.assertEqual(called[0]["operation"],"keyword.search")
        self.assertNotIn("primary_text",called[0])
        self.assertNotIn("write_intent_id",called[0])
        self.assertEqual(called[0]["target_account_id"],"12345")
