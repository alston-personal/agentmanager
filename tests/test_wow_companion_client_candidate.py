"""Static governance tests for the ported WoW Forever client candidate.

Does not pretend to execute WoW Lua, authenticate a Bridge or load an AddOn.
"""
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LUA = ROOT / "integrations/wow/AgentOSWoW/AgentOSWoW.lua"
TOC = ROOT / "integrations/wow/AgentOSWoW/AgentOSWoW.toc"
REPLY_TOC = ROOT / "integrations/wow/AgentOSWoW_R001/AgentOSWoW_R001.toc"
REPLY_LUA = ROOT / "integrations/wow/AgentOSWoW_R001/Reply.lua"


class WowCompanionClientCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lua = LUA.read_text(encoding="utf-8")
        cls.toc = TOC.read_text(encoding="utf-8")
        cls.reply_toc = REPLY_TOC.read_text(encoding="utf-8")
        cls.reply_lua = REPLY_LUA.read_text(encoding="utf-8")

    def test_forever_toc_and_one_shot_slot_are_preserved(self):
        self.assertIn("## Interface: 16001", self.toc)
        self.assertIn("AgentOSWoW.lua", self.toc)
        self.assertIn("## LoadOnDemand: 1", self.reply_toc)
        self.assertIn("Reply.lua", self.reply_toc)
        self.assertIn("AgentOSWoWReplySlot = nil", self.reply_lua)

    def test_existing_status_account_routes_preserved(self):
        for marker in (
            'wow.control.status',
            'wow.account.login.start',
            'wow.account.logout',
            'agentos.wow.status.reply/v1',
            'agentos.wow.account.reply/v1',
            'SLASH_AGENTOSWOW1 = "/agentos"',
        ):
            self.assertIn(marker, self.lua)

    def test_client_has_display_only_companion_branch(self):
        for marker in (
            'agentos.wow.companion.reply/v1',
            'data.action ~= "ui.answer"',
            "data.request_id ~= expectedAIRequestId",
            'handleCompanionAnswer(data)',
            'answerLine:SetText(data.answer)',
        ):
            self.assertIn(marker, self.lua)

    def test_question_only_stages_diagnostic_frames(self):
        self.assertIn('questionBox:Enable()', self.lua)
        self.assertIn('askButton:SetText("Stage question")', self.lua)
        self.assertIn('askButton:SetScript("OnClick", stageDiagnosticQuestion)', self.lua)
        self.assertIn('nextFrameButton:SetText("Show next frame")', self.lua)
        self.assertIn('nextFrameButton:Disable()', self.lua)
        self.assertIn('local expectedAIRequestId = nil', self.lua)
        self.assertIn('expectedAIRequestId = "ask-" .. tostring(id)', self.lua)
        self.assertIn('Bridge unverified', self.lua)
        self.assertNotIn('RunScript(', self.lua)
        self.assertNotIn('loadstring(', self.lua)

    def test_frame_layout_matches_existing_python_codec(self):
        self.assertIn('local QUESTION_CHUNK_BYTES = 54', self.lua)
        self.assertIn('local QUESTION_MAX_BYTES = 500', self.lua)
        self.assertIn('local QUESTION_MAX_PARTS = 16', self.lua)
        self.assertIn('string.char(0xA1) .. session .. bytePair(id)', self.lua)
        self.assertIn('string.char(index, total) .. part', self.lua)
        self.assertIn('if #cells > PROBE_MAX_CELLS then return nil end', self.lua)
        self.assertIn('Frame " .. stagedFrameIndex', self.lua)
        self.assertIn('No Bridge acknowledgment; advance manually', self.lua)

    def test_reply_slot_is_one_shot(self):
        self.assertIn('if replySlotUsed then', self.lua)
        self.assertIn('replySlotUsed = true', self.lua)
        self.assertIn('AgentOSWoWReplySlot = nil', self.lua)


if __name__ == "__main__":
    unittest.main()
