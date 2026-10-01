from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent_core.product_experience import ProductExperienceStore


class ProductExperienceTests(unittest.TestCase):
    def test_candidate_requires_reuse_before_promotion(self):
        with tempfile.TemporaryDirectory() as td:
            store=ProductExperienceStore('demo-product', Path(td))
            unit=store.upsert_candidate(
                experience_id='gui.url.semantic-open',
                kind='rule',
                claim='Use semantic URL open.',
                scope='browser navigation',
                source_experience=['receipt-1'],
                validation=['reproduced once'],
                confidence=0.9,
                state='validated_candidate',
            )
            self.assertEqual(unit['state'], 'validated_candidate')
            with self.assertRaises(ValueError):
                store.promote('gui.url.semantic-open', target_state='trusted', evidence=['later-run'])

            reused=store.record_reuse('gui.url.semantic-open', success=True, prevented_regression=True)
            self.assertEqual(reused['reuse']['hits'], 1)
            promoted=store.promote('gui.url.semantic-open', target_state='trusted', evidence=['later-run'])
            self.assertEqual(promoted['state'], 'trusted')

    def test_store_tracks_reuse_metrics(self):
        with tempfile.TemporaryDirectory() as td:
            store=ProductExperienceStore('demo-product', Path(td))
            store.upsert_candidate(
                experience_id='gui.postcondition',
                kind='pattern',
                claim='Verify a postcondition after GUI actions.',
                scope='interactive plans',
                source_experience=['receipt-1'],
                state='validated_candidate',
            )
            store.record_reuse('gui.postcondition', success=True)
            payload=store.load()
            self.assertEqual(payload['metrics']['validated_candidates_total'], 1)
            self.assertEqual(payload['metrics']['reuse_hits_total'], 1)
            self.assertEqual(payload['metrics']['reuse_success_total'], 1)


if __name__ == '__main__':
    unittest.main()
