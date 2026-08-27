import json
from pathlib import Path

from agentos_node.social_capability import CredentialStore, SocialCapability


class FakeTransport:
    def __init__(self):
        self.calls = []

    def request(self, method, url, *, params=None):
        params = dict(params or {})
        self.calls.append((method, url, params))
        if url.endswith('/me'):
            return {'id': 'threads-user-1', 'username': 'tester'}
        if url.endswith('/threads'):
            return {'id': 'creation-1'}
        if url.endswith('/threads_publish'):
            return {'id': 'thread-1'}
        if url.endswith('/thread-1'):
            return {'permalink': 'https://www.threads.net/@tester/post/example'}
        if 'graph.facebook.com' in url:
            if 'ig-1' in url:
                return {'id': 'ig-1', 'username': 'igtester'}
            return {'id': 'page-1', 'name': 'Page Tester'}
        raise AssertionError((method, url, params))


def _store(tmp_path: Path) -> CredentialStore:
    path = tmp_path / 'social-credentials.json'
    path.write_text(json.dumps({
        'threads/default': {'platform': 'threads', 'access_token': 'THREADS_SECRET'},
        'facebook/default': {'platform': 'facebook', 'access_token': 'FB_SECRET', 'page_id': 'page-1'},
        'instagram/default': {'platform': 'instagram', 'access_token': 'IG_SECRET', 'ig_id': 'ig-1'},
    }), encoding='utf-8')
    path.chmod(0o600)
    return CredentialStore(path)


def test_threads_identity_receipt_never_contains_secret(tmp_path):
    cap = SocialCapability(_store(tmp_path), FakeTransport())
    receipt = cap.execute('threads', 'identity', 'threads/default', {})
    assert receipt['ok'] is True
    assert receipt['platform_object_id'] == 'threads-user-1'
    assert 'THREADS_SECRET' not in json.dumps(receipt)
    assert receipt['credential_ref'] == 'threads/default'


def test_write_requires_explicit_approval(tmp_path):
    cap = SocialCapability(_store(tmp_path), FakeTransport())
    receipt = cap.execute('threads', 'publish', 'threads/default', {'text': 'hello'})
    assert receipt['ok'] is False
    assert receipt['error_code'] == 'write_not_approved'


def test_threads_controlled_publish_returns_secret_free_receipt(tmp_path):
    transport = FakeTransport()
    cap = SocialCapability(_store(tmp_path), transport)
    receipt = cap.execute('threads', 'publish', 'threads/default', {'text': 'hello', 'allow_write': True})
    assert receipt['ok'] is True
    assert receipt['platform_object_id'] == 'thread-1'
    assert receipt['permalink'].startswith('https://www.threads.net/')
    assert 'THREADS_SECRET' not in json.dumps(receipt)
    assert any(call[2].get('access_token') == 'THREADS_SECRET' for call in transport.calls)


def test_facebook_and_instagram_are_identity_only_until_verified(tmp_path):
    cap = SocialCapability(_store(tmp_path), FakeTransport())
    fb = cap.execute('facebook', 'identity', 'facebook/default', {})
    ig = cap.execute('instagram', 'identity', 'instagram/default', {})
    assert fb['ok'] is True and fb['platform_object_id'] == 'page-1'
    assert ig['ok'] is True and ig['platform_object_id'] == 'ig-1'

    fb_write = cap.execute('facebook', 'publish', 'facebook/default', {'text': 'x', 'allow_write': True})
    ig_write = cap.execute('instagram', 'publish', 'instagram/default', {'text': 'x', 'allow_write': True})
    assert fb_write['error_code'] == 'operation_not_yet_verified'
    assert ig_write['error_code'] == 'operation_not_yet_verified'
