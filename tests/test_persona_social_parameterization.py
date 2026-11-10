"""Contract tests for persona-parameterized social orchestration."""
import inspect
import os
import subprocess
import sys
import unittest

from agentos_node import persona_life


class PersonaSocialParameterizationTests(unittest.TestCase):
    def _probe(self, env):
        code = (
            "from scripts import mio_persona_social_loop_user as m;"
            "print(m.PERSONA_SLUG);"
            "print(m.PERSONA_ID);"
            "print(m.PERSONA_DISPLAY);"
            "print(','.join(m.PERSONA_HANDLES));"
            "print(m.STATE_DIR);"
            "print(m.PERSONA_ROOT)"
        )
        merged = os.environ.copy()
        merged.update(env)
        return subprocess.check_output(
            [sys.executable, "-c", code],
            text=True,
            env=merged,
        ).splitlines()

    def test_mio_defaults_are_backward_compatible(self):
        env = {
            "AGENTOS_PERSONA_SLUG": "",
            "AGENTOS_PERSONA_ID": "",
            "AGENTOS_PERSONA_DISPLAY": "",
            "AGENTOS_PERSONA_THREADS_HANDLES": "sunlake.milkcat,mio.milkcat",
        }
        rows = self._probe(env)
        self.assertEqual(rows[0], "sunlake-milkcat")
        self.assertEqual(rows[1], "sunlake-milkcat-ai-001")
        self.assertEqual(rows[2], "澪 / Mio")
        self.assertEqual(rows[3], "sunlake.milkcat,mio.milkcat")
        self.assertTrue(rows[4].endswith("/runtime/social/persona/sunlake-milkcat"))
        self.assertTrue(rows[5].endswith("/personas/sunlake-milkcat"))

    def test_oursong_identity_isolated_from_mio(self):
        rows = self._probe({
            "AGENTOS_PERSONA_SLUG": "oursong_alstonhuang",
            "AGENTOS_PERSONA_ID": "oursong-alstonhuang-001",
            "AGENTOS_PERSONA_DISPLAY": "oursong_alstonhuang",
            "AGENTOS_PERSONA_PROJECT_ID": "oursong-alstonhuang-persona-social",
            "AGENTOS_PERSONA_WRITE_PREFIX": "oursong",
            "AGENTOS_PERSONA_THREADS_HANDLES": "oursong_alstonhuang",
        })
        self.assertEqual(rows[:4], [
            "oursong_alstonhuang",
            "oursong-alstonhuang-001",
            "oursong_alstonhuang",
            "oursong_alstonhuang",
        ])
        self.assertTrue(rows[4].endswith("/runtime/social/persona/oursong_alstonhuang"))
        self.assertTrue(rows[5].endswith("/personas/oursong_alstonhuang"))

    def test_life_event_api_accepts_persona_id(self):
        params = inspect.signature(persona_life.maybe_generate_event).parameters
        self.assertIn("persona_id", params)
        self.assertEqual(params["persona_id"].default, "sunlake-milkcat-ai-001")


if __name__ == "__main__":
    unittest.main()
