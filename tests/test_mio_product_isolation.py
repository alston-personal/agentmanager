import importlib.util
import os
import pathlib
import tempfile
import unittest


MODULE = pathlib.Path(__file__).resolve().parents[1] / "scripts/prepare_mio_product_isolation.py"
spec = importlib.util.spec_from_file_location("mio_isolation", MODULE)
isolation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(isolation)


class IsolationTests(unittest.TestCase):
    def test_original_url_is_preserved_and_not_approved(self):
        with tempfile.TemporaryDirectory() as d:
            old = isolation.ROOT, isolation.GARMENTS, isolation.TASKS
            try:
                root = pathlib.Path(d)
                isolation.ROOT = root
                isolation.GARMENTS = root / "garments"
                isolation.TASKS = root / "isolation_jobs"
                (isolation.GARMENTS / "seeded").mkdir(parents=True)
                source = isolation.GARMENTS / "seeded" / "item.json"
                source.write_text('{"garmentId":"item-1","name":"Top with model and pants","layer":"upper_main","source":{"imageUrl":"https://example.com/look.jpg"}}', encoding="utf-8")
                task = isolation.build_task("item-1")
                self.assertEqual(task["state"], "pending")
                self.assertEqual(task["sourceImageUrl"], "https://example.com/look.jpg")
                self.assertIsNone(task["isolatedImageUrl"])
                self.assertIsNone(task["productIR"])
                self.assertEqual(isolation.build_task("item-1")["sourceFingerprint"], task["sourceFingerprint"])
                self.assertNotIn("tryOnSource", source.read_text())
            finally:
                isolation.ROOT, isolation.GARMENTS, isolation.TASKS = old


if __name__ == "__main__":
    unittest.main()
