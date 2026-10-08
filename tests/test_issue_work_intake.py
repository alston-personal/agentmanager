import importlib.util
import pathlib
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from issue_work_intake import eligible, intake

def item(labels=None,number=400,body="Action: 檢查連接埠 65534\nAcceptance: independent socket check"):
    return {"number":number,"state":"open","title":"Safe read-only probe","labels":[{"name":x} for x in (labels or [])],"body":body,"html_url":f"https://github.com/alston-personal/agentmanager/issues/{number}"}
APPROVED=["agentos:approved","agentos:lobster","agentos:readonly"]

class IssueIntakeTest(unittest.TestCase):
    def test_fail_closed(self):
        self.assertFalse(eligible(item(), "alston-personal/agentmanager")[0])
        for label in ["blocked","needs-approval","production-change"]:
            self.assertFalse(eligible(item(APPROVED+[label]),"alston-personal/agentmanager")[0])
        self.assertFalse(eligible(item(APPROVED,body="Action: rm -rf /\nAcceptance: done"),"alston-personal/agentmanager")[0])
        pr=item(APPROVED);pr["pull_request"]={};self.assertFalse(eligible(pr,"alston-personal/agentmanager")[0])
        wrong=item(APPROVED);wrong["html_url"]="https://github.com/evil/repo/issues/400";self.assertFalse(eligible(wrong,"alston-personal/agentmanager")[0])
    def test_register_once_and_never_repeat_completed(self):
        with tempfile.TemporaryDirectory() as d:
            state=pathlib.Path(d)/"ledger.json"
            one=intake([item(APPROVED)],repo="alston-personal/agentmanager",state=state,workspace=pathlib.Path(d))
            two=intake([item(APPROVED)],repo="alston-personal/agentmanager",state=state,workspace=pathlib.Path(d))
            self.assertEqual(one[0]["work_id"],"gh-issue-400-readonly")
            self.assertEqual(two[0]["status"],"accepted")
            import json
            self.assertEqual(len(json.loads(state.read_text())["items"]),1)

if __name__=="__main__":unittest.main()
