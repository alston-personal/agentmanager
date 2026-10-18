import unittest
from scripts.persona_gui_live_home_diagnostic import classify, classify_profile_nav

class GuiLiveHomeDiagnosticTest(unittest.TestCase):
    def test_login_ui_needs_auth(self):
        self.assertEqual(classify(final_url="https://www.threads.com/",http_status=200,page_title="",visible_login=True)[0],"AUTH_REQUIRED")
    def test_no_login_prompt_does_not_verify_identity(self):
        self.assertEqual(classify(final_url="https://www.threads.com/",http_status=200,page_title="",visible_login=False)[0],"UNVERIFIED")
    def test_redirect_and_http_fail_closed(self):
        self.assertEqual(classify(final_url="https://example.com/",http_status=200,page_title="",visible_login=False)[0],"BLOCKED")
        self.assertEqual(classify(final_url="https://www.threads.com/",http_status=403,page_title="",visible_login=False)[0],"BLOCKED")
    def test_profile_nav_fails_closed(self):
        self.assertEqual(classify_profile_nav([])[0],"IDENTITY_UNVERIFIED")
        self.assertEqual(classify_profile_nav(["https://www.threads.com/@oursong_alstonhuang"])[0],"ACCOUNT_MISMATCH")
        self.assertEqual(classify_profile_nav(["https://www.threads.com/@mio.milkcat"])[0],"PROFILE_NAV_MATCH_ONLY")
        self.assertEqual(classify_profile_nav(["https://www.threads.com/@mio.milkcat","https://www.threads.com/@other"])[0],"IDENTITY_UNVERIFIED")
        self.assertEqual(classify_profile_nav(["https://evil.example/@mio.milkcat"])[0],"IDENTITY_UNVERIFIED")
if __name__=="__main__": unittest.main()
