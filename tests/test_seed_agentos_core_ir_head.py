import unittest

from agent_core.project_continuation_index import validate_publish_params
from scripts.seed_agentos_core_ir_head import INDEX_ID, IR_ID, build_seed_payload


class SeedAgentosCoreIrHeadTests(unittest.TestCase):
    def test_seed_uses_existing_canonical_publish_contract(self):
        project_id, execution_head, continuation = validate_publish_params(build_seed_payload())
        canonical_ir = continuation["canonical_ir"]

        self.assertEqual(project_id, "agentos-core")
        self.assertEqual(execution_head["schema"], "agentos.execution-head/v1")
        self.assertEqual(execution_head["index_id"], INDEX_ID)
        self.assertEqual(continuation["index_id"], INDEX_ID)
        self.assertEqual(canonical_ir["schema_version"], "agentos.ir/v1")
        self.assertEqual(canonical_ir["index_id"], INDEX_ID)
        self.assertEqual(canonical_ir["ir_id"], IR_ID)
        self.assertIsNone(canonical_ir["parent_ir_id"])
        self.assertTrue(canonical_ir["goal"])
        self.assertTrue(continuation["recommended_action"])

    def test_seed_preserves_ir_first_and_identity_fences(self):
        canonical_ir = build_seed_payload()["continuation"]["canonical_ir"]
        constraints = "\n".join(canonical_ir["constraints"])
        decisions = "\n".join(canonical_ir["decisions"])

        self.assertIn("Workspace membership is only a hydration gate", constraints)
        self.assertIn("fail closed", constraints)
        self.assertIn("built-in Gemini executor is distinct", constraints)
        self.assertIn("existing project continuation publisher", decisions)
        self.assertNotIn("zeus-writer", str(canonical_ir).casefold())
        self.assertNotIn("privacy-guard", str(canonical_ir).casefold())


if __name__ == "__main__":
    unittest.main()
