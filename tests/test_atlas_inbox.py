import tempfile
import unittest
from pathlib import Path

from agent_core.atlas_inbox import consolidate_atlas_inbox, submit_experience_card


class AtlasInboxTests(unittest.TestCase):
    def test_append_only_submission_and_deduplicated_consolidation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            c1 = submit_experience_card(
                root,
                kind="pitfall",
                title="No hollow fallback",
                summary="Raise KeyError instead of returning BasePDCAWorker.",
                source_model="gemini-4",
            )
            c2 = submit_experience_card(
                root,
                kind="pitfall",
                title="No hollow fallback",
                summary="Duplicate from concurrent ChatGPT shard.",
                source_model="gpt-5",
            )
            c3 = submit_experience_card(
                root,
                kind="growth_observation",
                title="G3 anti-hollow uplift",
                summary="Concrete resolution rose from 82.6% to 100%.",
                evidence_refs=["PR #2358", "PR #2360"],
            )
            self.assertTrue(c1.is_file() and c2.is_file() and c3.is_file())

            res = consolidate_atlas_inbox(root)
            self.assertEqual(res["processed"], 2)
            self.assertEqual(res["skipped_duplicates"], 1)
            self.assertEqual(res["promoted_growth"], 1)

            # Inbox should be drained and archived into processed/
            inbox_dir = root / "personas" / "system-atlas" / "inbox"
            self.assertEqual(list(inbox_dir.glob("*.json")), [])
            self.assertEqual(len(list((inbox_dir / "processed").glob("*.json"))), 3)


if __name__ == "__main__":
    unittest.main()
