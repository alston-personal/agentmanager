from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.inspect_antigravity_hook_contract import inspect


class InspectAntigravityHookContractTests(unittest.TestCase):
    def test_reports_product_and_bounded_token_contexts(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            app = root / "resources" / "app"
            bundle = app / "out" / "jetskiAgent" / "main.js"
            binary = app / "extensions" / "antigravity" / "bin" / "language_server_test"
            bundle.parent.mkdir(parents=True)
            binary.parent.mkdir(parents=True)
            (app / "product.json").write_text(
                json.dumps({"version": "1.2.3", "commit": "abc", "dataFolderName": ".ag"}),
                encoding="utf-8",
            )
            bundle.write_bytes(b"PreInvocation ephemeralMessage hooks.json")
            binary.write_bytes(b"injectSteps\x00PreInvocation")

            result = inspect(root)

            self.assertEqual(result["schema"], "agentos.antigravity-hook-runtime-contract/v1")
            self.assertEqual(result["product"]["version"], "1.2.3")
            self.assertEqual(result["tokens"]["PreInvocation"], 2)
            self.assertEqual(result["tokens"]["injectSteps"], 1)
            contexts = result["files"][0]["contexts"]["PreInvocation"]
            self.assertLessEqual(len(contexts), 6)
            self.assertIn("ephemeralMessage", contexts[0])


if __name__ == "__main__":
    unittest.main()

