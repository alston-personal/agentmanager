#!/usr/bin/env python3
"""Tests for AgentOS Codebase Atlas & Semantic Index Engine."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.atlas_indexer import (
    locate,
    record_trace,
    scan_directory,
    get_status,
    bootstrap_core_topics
)


class TestAtlasIndexer(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.orig_data_root = os.environ.get("AGENT_DATA_ROOT")
        os.environ["AGENT_DATA_ROOT"] = self.test_dir

    def tearDown(self):
        if self.orig_data_root is not None:
            os.environ["AGENT_DATA_ROOT"] = self.orig_data_root
        else:
            os.environ.pop("AGENT_DATA_ROOT", None)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_bootstrap_and_locate_topics(self):
        bootstrap_core_topics()
        status = get_status()
        self.assertGreaterEqual(status["topics_count"], 5)

        hits = locate("Mio threads 回覆")
        self.assertTrue(any("mio" in h["title"].lower() or "mio" in h.get("topic_id", "") for h in hits))

    def test_record_and_locate_trace(self):
        record_trace(
            query="test nginx 403 error routing",
            answer_summary="Fixed dist directory missing index.html",
            files=["scripts/sync_persona_portal.py"]
        )
        hits = locate("test nginx 403 error")
        self.assertTrue(len(hits) > 0)
        self.assertEqual(hits[0]["type"], "trace_hit")
        self.assertIn("Fixed dist directory", hits[0]["summary"])

    def test_scan_directory_incremental(self):
        # Create a mock python script in test_dir
        scripts_dir = Path(self.test_dir) / "scripts"
        scripts_dir.mkdir(parents=True)
        py_file = scripts_dir / "sample_service.py"
        py_file.write_text('"""Sample service for indexing."""\ndef run_service():\n    pass\n', encoding="utf-8")

        res1 = scan_directory(Path(self.test_dir))
        self.assertEqual(res1["scanned"], 1)
        self.assertEqual(res1["updated"], 1)

        # Rescan without modification -> should skip
        res2 = scan_directory(Path(self.test_dir))
        self.assertEqual(res2["scanned"], 1)
        self.assertEqual(res2["updated"], 0)
        self.assertEqual(res2["skipped"], 1)


if __name__ == "__main__":
    unittest.main()

