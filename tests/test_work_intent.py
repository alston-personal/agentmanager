from __future__ import annotations

import unittest

from agent_core.work_intent import WORK_INTENT_REF_SCHEMA, parse_work_intent_ref


class WorkIntentRefTests(unittest.TestCase):
    def test_accepts_bounded_content_addressed_reference(self):
        ref = parse_work_intent_ref(
            {
                "schema": WORK_INTENT_REF_SCHEMA,
                "product_id": "zeus-writer",
                "state_key": "review-existing-draft",
                "revision": 2,
                "digest": "sha256:" + "c" * 64,
            }
        )
        self.assertEqual(ref.product_id, "zeus-writer")
        self.assertEqual(ref.revision, 2)
        self.assertTrue(ref.identity.endswith("sha256:" + "c" * 64))

    def test_rejects_path_url_and_execution_fields(self):
        invalid_refs = [
            {
                "schema": WORK_INTENT_REF_SCHEMA,
                "product_id": "https://example.test",
                "state_key": "review",
                "revision": 1,
                "digest": "sha256:" + "d" * 64,
            },
            {
                "schema": WORK_INTENT_REF_SCHEMA,
                "product_id": "zeus-writer",
                "state_key": "../review",
                "revision": 1,
                "digest": "sha256:" + "d" * 64,
            },
            {
                "schema": WORK_INTENT_REF_SCHEMA,
                "product_id": "zeus-writer",
                "state_key": "review",
                "revision": 1,
                "digest": "sha256:" + "d" * 64,
                "command": "publish",
            },
        ]
        for value in invalid_refs:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_work_intent_ref(value)

    def test_rejects_invalid_digest_and_revision(self):
        for value in (
            {
                "schema": WORK_INTENT_REF_SCHEMA,
                "product_id": "zeus-writer",
                "state_key": "review",
                "revision": 0,
                "digest": "sha256:" + "e" * 64,
            },
            {
                "schema": WORK_INTENT_REF_SCHEMA,
                "product_id": "zeus-writer",
                "state_key": "review",
                "revision": 1,
                "digest": "sha256:not-a-digest",
            },
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_work_intent_ref(value)


if __name__ == "__main__":
    unittest.main()
