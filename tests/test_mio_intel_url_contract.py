"""Strict URL parsing for existing Mio Intelligence Hub; no network or writes."""
import unittest
from scripts.mio_intel_hub import parse_and_validate_url


class MioIntelUrlContract(unittest.TestCase):
    def test_share_is_candidate_not_provider_id(self):
        data = parse_and_validate_url("https://www.threads.com/share/GdMiITUe6/")
        self.assertEqual(data["media_id"], "share:GdMiITUe6")
        self.assertEqual(data["id_provenance"], "share_url_unresolved")

    def test_untrusted_host_and_redirect_query_rejected(self):
        urls = (
            "https://example.org/https://www.threads.com/@abc/post/X",
            "https://www.threads.com.evil.org/@abc/post/X",
            "https://www.threads.com/@abc/post/X?redirect=evil",
            "http://www.threads.com/@abc/post/X",
        )
        for url in urls:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    parse_and_validate_url(url)

    def test_regular_url_preserves_unverified_discovery_provenance(self):
        data = parse_and_validate_url("https://www.threads.net/@sample/post/AbCd")
        self.assertEqual(data["username"], "sample")
        self.assertEqual(data["id_provenance"], "shortcode_derived_unverified")
        self.assertNotEqual(data["media_id"], "AbCd")


if __name__ == "__main__":
    unittest.main()
