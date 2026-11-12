import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from scripts.audit_studio_nginx_redacted import parse_nginx, root_class, run_nginx

class StudioNginxRedactedAuditTests(unittest.TestCase):
    def test_exact_studio_server_only_and_redaction(self):
        source = """
# configuration file /etc/nginx/sites-enabled/anything:
server {
 listen 443 ssl;
 server_name other.example.org;
 root /srv/other;
}
server {
 listen 443 ssl;
 server_name studio.milkcat.org;
 ssl_certificate_key /very/private/path.pem;
 root /home/ubuntu/zeus-writer/website/dist;
 location / {
   try_files $uri $uri/ /index.html;
 }
 location /dashboard/api/auth/session {
   proxy_pass http://127.0.0.1:3000/secret-token;
   proxy_set_header Authorization "Bearer secret";
 }
 location /a-private-internal-location {
   alias /top/secret/dir/;
 }
}
"""
        blocks = parse_nginx(source)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["roots"], ["legacy-zeuswriter"])
        self.assertTrue(blocks[0]["index_fallback"])
        self.assertEqual(blocks[0]["proxies"], ["loopback"])
        serialized = json.dumps(blocks)
        for private in ("secret-token", "Bearer", "/very/private", "/a-private", "/top/secret"):
            self.assertNotIn(private, serialized)

    def test_other_root_path_is_not_disclosed(self):
        self.assertEqual(root_class("/sensitive/unregistered/secret"), "other")
        self.assertEqual(root_class("/home/ubuntu/studio-web/dist"), "canonical-studio")

    @patch("scripts.audit_studio_nginx_redacted.subprocess.run")
    def test_permission_failure_does_not_expose_stderr(self, run):
        run.return_value = SimpleNamespace(returncode=1, stdout="", stderr="private-key: secret")
        result = run_nginx()
        self.assertFalse(result["available"])
        self.assertNotIn("secret", json.dumps(result))

if __name__ == "__main__":
    unittest.main()
