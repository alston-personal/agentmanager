import unittest

from agentos_node.social.platform_matrix import platform_capabilities, platform_supports


class SocialPlatformMatrixTests(unittest.TestCase):
    def test_threads_live_capabilities_are_explicit(self):
        for op in ("identity.read", "post.read", "post.insights.read", "replies.read", "keyword.search", "publish", "reply"):
            self.assertTrue(platform_supports("threads", op), op)

    def test_follow_is_not_falsely_claimed(self):
        self.assertFalse(platform_supports("threads", "follow"))
        self.assertFalse(platform_supports("threads", "unfollow"))

    def test_other_platforms_are_replaceable_but_not_claimed_live(self):
        self.assertFalse(platform_supports("instagram", "publish"))
        self.assertFalse(platform_supports("facebook", "publish"))
        self.assertIn("publish", platform_capabilities("instagram"))


if __name__ == "__main__":
    unittest.main()
