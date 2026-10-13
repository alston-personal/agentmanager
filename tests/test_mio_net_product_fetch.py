import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("fetch_isolate", SCRIPTS / "fetch_and_isolate_mio_net_product.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class FetchIsolationTests(unittest.TestCase):
    def test_untrusted_urls_rejected(self):
        for url in [
            "http://net.wimg.tw/a.png",
            "https://net.wimg.tw.evil.test/a.png",
            "https://127.0.0.1/a.png",
            "https://user@net.wimg.tw/a.png",
            "https://net.wimg.tw:444/a.png",
            "https://www.net-fashion.net/product/1",
        ]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                mod.validate_url(url)

    def test_valid_net_cdn_url(self):
        mod.validate_url("https://s-net.wimg.tw//act/32235-711-1024-01.jpg?v=32570")

    def test_unknown_and_approved_jobs_do_not_download(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)
            (root/"isolation_jobs").mkdir()
            with patch.object(mod, "ROOT", root):
                with self.assertRaises(FileNotFoundError):
                    mod.run_job("missing")
                (root/"isolation_jobs"/"hat.json").write_text(json.dumps({
                    "schema":mod.SCHEMA, "garmentId":"hat", "state":"approved",
                    "sourceImageUrl":"https://net.wimg.tw/test.jpg",
                }))
                with patch.object(mod, "download") as downloader:
                    with self.assertRaisesRegex(ValueError, "immutable"):
                        mod.run_job("hat")
                    downloader.assert_not_called()

    def test_job_requires_net_image_url(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)
            (root/"isolation_jobs").mkdir()
            (root/"isolation_jobs"/"hat.json").write_text(json.dumps({
                "schema":mod.SCHEMA, "garmentId":"hat", "state":"pending",
                "sourceImageUrl":"https://www.net-fashion.net/product/731541",
            }))
            with patch.object(mod, "ROOT", root):
                with self.assertRaisesRegex(ValueError, "unapproved"):
                    mod.run_job("hat")

if __name__ == "__main__":
    unittest.main()
