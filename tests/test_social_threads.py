import unittest

from agent_core.social_threads import ThreadsSourceError, parse_public_post_html


class SocialThreadsTest(unittest.TestCase):
    def test_extracts_author_text_and_canonical_url(self):
        html = '''<html><head>
        <meta property="og:title" content="Nico (@nico1e.16) on Threads" />
        <meta property="og:description" content="最近一直在想，工作是不是該換個方向？" />
        </head></html>'''
        url = "https://www.threads.com/@nico1e.16/post/DcWVvpwGTSh"
        data = parse_public_post_html(html, url)
        self.assertEqual(data["type"], "threads")
        self.assertEqual(data["author"], "Nico")
        self.assertEqual(data["username"], "nico1e.16")
        self.assertEqual(data["text"], "最近一直在想，工作是不是該換個方向？")
        self.assertEqual(data["url"], url)

    def test_json_ld_wins_when_available(self):
        html = '''<html><head><meta property="og:description" content="fallback" /></head>
        <script type="application/ld+json">{"text":"日本語の投稿です。","author":{"name":"山田"}}</script></html>'''
        data = parse_public_post_html(html, "https://www.threads.net/@yamada/post/ABC123")
        self.assertEqual(data["text"], "日本語の投稿です。")
        self.assertEqual(data["author"], "山田")

    def test_rejects_non_threads_url(self):
        with self.assertRaises(ThreadsSourceError):
            parse_public_post_html('<meta property="og:description" content="x">', 'https://example.com/post/1')

    def test_requires_post_text(self):
        with self.assertRaises(ThreadsSourceError):
            parse_public_post_html('<title>Threads</title>', 'https://www.threads.net/@x/post/ABC')


if __name__ == '__main__':
    unittest.main()
