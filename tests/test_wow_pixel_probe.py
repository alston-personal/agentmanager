from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
LUA=ROOT/"integrations"/"wow"/"AgentOSWoW"/"AgentOSWoW.lua"
class WoWPixelProbeStaticTest(unittest.TestCase):
    def test_status_only_and_no_fake_online(self):
        src=LUA.read_text(encoding="utf-8")
        self.assertIn('{"action":"wow.control.status","session":"',src)
        self.assertIn('local PROBE_MAX_CELLS = 200',src)
        self.assertIn('sendStatusProbe',src)
        self.assertIn('awaiting verified Bridge',src)
        self.assertIn("questionBox:Disable()",src)
        self.assertIn("askButton:Disable()",src)
        self.assertNotIn("RunMacroText",src)
        self.assertNotIn("bypassPermissions",src)
if __name__=="__main__":unittest.main()
