from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
class WowInstallerContractTests(unittest.TestCase):
    def test_fail_closed_preflight(self):
        src=(ROOT/'scripts/wow_agentos_installer_preflight.ps1').read_text(encoding='utf-8')
        for state in ('NODE_UNENROLLED','NODE_NOT_INSTALLED','NODE_AUTH_INVALID','NODE_VERIFIED','NODE_UNAVAILABLE','CROSS_REALM_UNAVAILABLE','WOW_CLIENT_UNSUPPORTED'):
            self.assertIn(state,src)
        self.assertIn('agentos-client.cmd',src)
        self.assertIn(' verify ',src)
        for forbidden in ('Remove-Item','-SwitchRealm','Set-Content','Invoke-WebRequest','Invoke-RestMethod'):
            self.assertNotIn(forbidden,src)
    def test_launcher_disclaims_real_install(self):
        cmd=(ROOT/'scripts/WoW-AgentOS-Setup.cmd').read_text(encoding='utf-8')
        self.assertIn('full installer is not released',cmd)
if __name__=='__main__':unittest.main()
