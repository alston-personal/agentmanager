import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentos_node.provider_terminal_health import (
    gemini_identity, blocked, record_block, breaker_path
)


class SharedTerminalHealthTests(unittest.TestCase):
    def test_shared_breaker_is_durable_and_runtime_version_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cli = root / "gemini"
            cli.write_bytes(b"v1")
            home = root / "home"
            (home / ".gemini").mkdir(parents=True)
            (home / ".gemini/settings.json").write_text(
                json.dumps({"security":{"auth":{"selectedType":"oauth-personal"}}})
            )
            first = gemini_identity(cli, home=home)
            self.assertFalse(blocked(first, data_root=root))
            record_block(first, data_root=root)
            self.assertTrue(blocked(first, data_root=root))
            record = json.loads(breaker_path(data_root=root).read_text())
            self.assertEqual(record["classification"], "OAUTH_CLIENT_UNSUPPORTED")
            self.assertEqual(breaker_path(data_root=root).stat().st_mode & 0o777, 0o600)
            cli.write_bytes(b"changed cli binary")
            second = gemini_identity(cli, home=home)
            self.assertNotEqual(first, second)
            self.assertFalse(blocked(second, data_root=root))
            (home / ".gemini/settings.json").write_text(
                json.dumps({"security":{"auth":{"selectedType":"api-key"}}})
            )
            third = gemini_identity(cli, home=home)
            self.assertNotEqual(second, third)
            self.assertFalse(blocked(third, data_root=root))

    def test_two_consumers_share_exact_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            from capabilities.wardrobe_visual_review.gemini_backend import (
                _is_terminal_oauth_blocked, _record_terminal_oauth
            )
            from agentos_node.provider_terminal_health import blocked
            with patch.dict("os.environ", {"AGENT_DATA_ROOT": tmp}):
                _record_terminal_oauth("fixed-identity")
                self.assertTrue(_is_terminal_oauth_blocked("fixed-identity"))
                self.assertTrue(blocked("fixed-identity"))
                self.assertFalse(blocked("other-identity"))


if __name__ == "__main__":
    unittest.main()
