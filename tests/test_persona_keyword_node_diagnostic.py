import json
import tempfile
import unittest
from pathlib import Path
from scripts.persona_keyword_node_diagnostic import run_probe


class NodeDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root=Path(self.tmp.name)
        self.env=root/"social-runtime.env"
        self.creds=root/"credentials.json"
        self.env.write_text('AGENTOS_SOCIAL_PRODUCTS_JSON={"galaxy":{"api_key":"dummy"}}\n')
        self.creds.write_text(json.dumps({"bindings":{"galaxy:threads:persona:12345":{
            "platform":"threads", "product_id":"galaxy","auth_profile":"persona",
            "username":"mio.milkcat","provider_account_id":"12345"}}}))
    def tearDown(self):
        self.tmp.cleanup()
    def run_test(self, reader):
        return run_probe("散步", env_path=self.env, credentials_path=self.creds, read_status=reader)
    def test_real_social_read_shape_is_unverified(self):
        def reader(req):
            self.assertEqual(req["operation"],"keyword.search")
            return 200,{"schema":"agentos.social-receipt/v1","ok":True,
                "operation":"keyword.search","platform":"threads",
                "account_binding_id":req["account_binding_id"],
                "target_account_id":"12345","receipt_id":"real123",
                "result":{"items":[{"id":"888","username":"stranger","text":"personal text"}]}}
        result=self.run_test(reader)
        self.assertEqual(result["reason"],"EXTERNAL_POST_PROVENANCE_REQUIRED")
        self.assertFalse(result["write_performed"])
        self.assertNotIn("personal text",json.dumps(result))
        self.assertFalse(result["node_verified"])
    def test_missing_config_blocks(self):
        self.env.unlink()
        self.assertEqual(self.run_test(lambda req:None)["reason"],"RUNTIME_CONFIG_UNAVAILABLE")
    def test_account_isolation_blocks(self):
        data=json.loads(self.creds.read_text())
        data["bindings"]["galaxy:threads:persona:12345"]["username"]="oursong_alstonhuang"
        self.creds.write_text(json.dumps(data))
        self.assertEqual(self.run_test(lambda req:None)["reason"],"BINDING_OR_PRODUCT_KEY_UNAVAILABLE")
    def test_denied_scope_classification(self):
        def reader(req):
            return 200,{"ok":False,"error_code":"OAuth permission missing"}
        result=self.run_test(reader)
        self.assertEqual(result["reason"],"AUTH_SCOPE_REQUIRED")
