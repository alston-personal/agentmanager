"""Ensure the production Oracle workflow really includes tab-class receipt."""
import unittest
from pathlib import Path

class MioTabClassificationWorkflowTest(unittest.TestCase):
    def test_classification_present_in_main_workflow(self):
        source=Path(".github/workflows/mio-gui-live-home-diagnostic.yml").read_text(encoding="utf-8")
        self.assertIn("mio_9224_tab_class_",source)
        self.assertIn("THREADS_MESSAGES",source)
        self.assertIn("THREADS_HOME",source)
        self.assertIn("THREADS_PROFILE_OR_POST",source)
        self.assertIn("BLANK",source)
        self.assertIn("assert sum(counts.values()) == len(pages)",source)
        self.assertNotIn("/json/close/",source)
if __name__=="__main__": unittest.main()
