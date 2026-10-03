import json
import tempfile
import unittest
from pathlib import Path

from agentos_node.mio_receipt_read import read_result


class MioReceiptReadTests(unittest.TestCase):
    KEY = "mio-post-20260922-small-discoveries-v1"

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_reads_matching_saved_result(self):
        record = {"schema": "agentos.mio-publish-result/v1", "post_key": self.KEY,
                  "platform_object_id": "18356065492302036",
                  "permalink": "https://www.threads.com/@sunlake.milkcat/post/DdgAUKMlH-X"}
        (self.root / (self.KEY + ".json")).write_text(json.dumps(record))
        self.assertEqual(read_result(self.KEY, self.root), record)

    def test_missing_result_does_not_publish(self):
        with self.assertRaises(FileNotFoundError):
            read_result(self.KEY, self.root)

    def test_rejects_path_traversal_and_mismatched_key(self):
        with self.assertRaises(ValueError):
            read_result("../private", self.root)
        path = self.root / (self.KEY + ".json")
        path.write_text(json.dumps({"schema": "agentos.mio-publish-result/v1", "post_key": "different"}))
        with self.assertRaises(ValueError):
            read_result(self.KEY, self.root)

    def test_rejects_symlink(self):
        target = self.root / "target.json"
        target.write_text("{}")
        (self.root / (self.KEY + ".json")).symlink_to(target)
        with self.assertRaises(ValueError):
            read_result(self.KEY, self.root)


if __name__ == "__main__":
    unittest.main()
