import io
import socket
from urllib.error import URLError

from scripts.inspect_distributed_control_plane import probe


class Response(io.BytesIO):
    def __init__(self, status, body, headers=None):
        super().__init__(body)
        self.status = status
        self.headers = headers or {}


def test_probe_rejects_token_in_html(monkeypatch):
    monkeypatch.setattr('scripts.inspect_distributed_control_plane.urlopen',
                        lambda *a, **k: Response(200, b'Node Map test-credential', {'X-Robots-Tag': 'noindex'}))
    result = probe('http://test/', 'test-credential', kind='shell')
    assert not result['ok'] and not result['credential_absent']
    assert 'test-credential' not in str(result)


def test_probe_preserves_dns_failure(monkeypatch):
    def fail(*a, **k):
        raise URLError(socket.gaierror('test DNS failure'))
    monkeypatch.setattr('scripts.inspect_distributed_control_plane.urlopen', fail)
    assert probe('http://test/', 'test-credential', kind='shell')['error'] == 'dns_error'


def test_approval_probe_sends_no_real_code(monkeypatch):
    def respond(request, **kwargs):
        assert request.data == b'{}'
        return Response(400, b'{"error": "code is required"}')
    monkeypatch.setattr('scripts.inspect_distributed_control_plane.urlopen', respond)
    result = probe('http://test/v1/nodes/approve', 'test-credential', kind='approval')
    assert result['ok'] and not result['real_enrollment_mutated']
