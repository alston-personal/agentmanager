import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from scripts import gaia_intake_probe


class GaiaRunnerProbeTest(unittest.TestCase):
    def test_probe_is_bounded_and_reports_non_authority(self):
        review = {
            "schema": "agentos.gaia-review/v1",
            "content_hash": "a" * 64,
            "decision": {"disposition": "NEEDS_EVIDENCE", "canonical_parent": None},
        }
        with patch.object(gaia_intake_probe, "examine", return_value={"review": review}) as examine:
            output = io.StringIO()
            with redirect_stdout(output):
                status = gaia_intake_probe.main()
        self.assertEqual(status, 0)
        self.assertEqual(examine.call_args.args[0], {
            "title": "Personal Device Secretary", "kind": "project",
            "related_asset_ids": ["project://mobile-node"],
        })
        self.assertIn("gaia_intake_probe=PASS", output.getvalue())
        self.assertIn("gaia_intake_execution_authorized=false", output.getvalue())
        self.assertIn("gaia_intake_creation_authorized=false", output.getvalue())
        self.assertNotIn("work_item_registered", output.getvalue())


if __name__ == "__main__":
    unittest.main()
