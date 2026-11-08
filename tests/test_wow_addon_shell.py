import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ADDON=ROOT/"integrations"/"wow"/"AgentOSWoW"

class WowAddonShellTest(unittest.TestCase):
    def test_loadable_native_ui_shell_has_no_fake_agent_response(self):
        toc=(ADDON/"AgentOSWoW.toc").read_text(encoding="utf-8")
        lua=(ADDON/"AgentOSWoW.lua").read_text(encoding="utf-8")
        self.assertIn("## Interface: 16001",toc)
        self.assertIn("AgentOSWoW.lua",toc)
        self.assertIn('"/agentos"',lua)
        self.assertIn('createPanel()',lua)
        self.assertIn("questionBox:Disable()",lua)
        self.assertIn("askButton:Disable()",lua)
        self.assertIn("Bridge: not connected",lua)
        for forbidden in ("RunMacroText","CastSpellByName","SendChatMessage","loadstring(","bypassPermissions","http://"):
            self.assertNotIn(forbidden,lua)

if __name__=="__main__":
    unittest.main()
