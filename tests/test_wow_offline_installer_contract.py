from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'scripts'
ADDONS=ROOT/'integrations'/'wow'


class WowOfflineInstallerContractTests(unittest.TestCase):
    def test_installer_requires_existing_node_and_explicit_consent(self):
        script=(SCRIPTS/'wow_agentos_install.ps1').read_text(encoding='utf-8')
        for required in (
            'NODE_VERIFIED', "wow_client -ne 'forever'", 'ConfirmInstall',
            'Read-Host', 'NOT_APPROVED', 'CLOSE_WOW_BEFORE_CHANGING_ADDONS',
            'COPY_HASH_MISMATCH', 'Get-FileHash', 'Move-Item', 'Remove-Item',
            'ADDON_ALREADY_EXISTS', 'AgentOSWoW_R001', 'AGENTOS_WOW_INSTALLER',
            'ADDON_CONTENT_CHANGED_REFUSE_UNINSTALL',
        ):
            self.assertIn(required,script)
        for forbidden in ('Invoke-WebRequest','Invoke-RestMethod','node_token =','agentos-client.cmd join'):
            self.assertNotIn(forbidden,script)

    def test_installer_validates_package_manifest_before_install(self):
        src=(SCRIPTS/'wow_agentos_install.ps1').read_text(encoding='utf-8')
        self.assertEqual(src.count('function Assert-BundleIntegrity'), 1)
        self.assertEqual(src.count('function Get-SafeDirectory'), 1)
        for required in ('manifest.json', 'BUNDLE_HASH_MISMATCH',
                         'BUNDLE_MANIFEST_MISSING', 'BUNDLE_UNSAFE_FILE',
                         'Assert-BundleIntegrity', 'files_sha256'):
            self.assertIn(required, src)
        self.assertLess(src.index(' Assert-BundleIntegrity'),
                        src.index(' $staged=New-Object'))

    def test_root_launcher_is_present_and_routes_to_existing_setup(self):
        root_launcher=(ROOT/'Install-AgentOS-WoW.cmd').read_text(encoding='utf-8')
        self.assertIn('scripts\\WoW-AgentOS-Setup.cmd', root_launcher)
        self.assertIn('call ', root_launcher)
        self.assertIn('exit /b %ERRORLEVEL%', root_launcher)
        package_script=(SCRIPTS/'build_wow_offline_installer.py').read_text(encoding='utf-8')
        self.assertIn('"Install-AgentOS-WoW.cmd"', package_script)

    def test_launcher_uses_installer_instead_of_preflight_only(self):
        launcher=(SCRIPTS/'WoW-AgentOS-Setup.cmd').read_text(encoding='utf-8')
        self.assertIn('wow_agentos_install.ps1', launcher)
        self.assertIn('-Mode Install', launcher)
        self.assertIn('wow_agentos_select_game.ps1', launcher)
        self.assertIn('WoW Forever was not found or the selection script was blocked', launcher)

    def test_windows_launcher_handles_execution_policy_and_invalid_selector(self):
        launcher=(SCRIPTS/'WoW-AgentOS-Setup.cmd').read_text(encoding='utf-8')
        self.assertEqual(launcher.count('-ExecutionPolicy Bypass'), 2)
        self.assertIn('2^>nul', launcher)
        self.assertIn('if not defined WOWROOT goto no_game', launcher)
        self.assertIn('if not exist "%WOWROOT%\\_forever_\\Wow.exe" goto no_game', launcher)
        self.assertIn('if not exist "%WOWROOT%\\_forever_\\Interface\\AddOns\\" goto no_game', launcher)
        self.assertIn('Group Policy', launcher)
        self.assertNotIn('Set-ExecutionPolicy', launcher)

    def test_addon_sources_are_complete_and_version_marked(self):
        main=ADDONS/'AgentOSWoW'
        reply=ADDONS/'AgentOSWoW_R001'
        self.assertTrue((main/'AgentOSWoW.lua').is_file())
        self.assertTrue((reply/'Reply.lua').is_file())
        self.assertIn('## Interface: 16001',
                      (main/'AgentOSWoW.toc').read_text(encoding='utf-8'))
        self.assertIn('## LoadOnDemand: 1',
                      (reply/'AgentOSWoW_R001.toc').read_text(encoding='utf-8'))


if __name__=='__main__':
    unittest.main()
