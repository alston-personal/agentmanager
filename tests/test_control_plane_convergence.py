"""HTTP acceptance against real, isolated Realm and token stores."""
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from agent_core.client_auth import ClientTokenStore
from agent_core.companion_web import render_companion_html
from agent_core.distributed_control_plane import DistributedControlPlane
from agent_core.distributed_gateway import DistributedGatewayServer, DistributedGatewayService
from agent_core.realm_fabric import RealmFabricStore


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    monkeypatch.setenv('AGENT_DATA_ROOT', str(tmp_path))
    fabric = RealmFabricStore()
    fabric.initialize_realm('test-realm')
    store = DistributedControlPlane(tmp_path / 'control.sqlite3')
    server = DistributedGatewayServer(('127.0.0.1', 0), DistributedGatewayService(store), token='test-root-only')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def request(path, token=None, body=None, method=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        req = Request(f'http://127.0.0.1:{server.server_port}' + path,
                      data=json.dumps(body).encode() if body is not None else None,
                      headers=headers, method=method)
        try:
            response = urlopen(req, timeout=3)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, response.headers, response.read().decode()
    yield request, fabric, store
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def test_public_shell_never_exposes_credentials(gateway):
    request, _, _ = gateway
    assert 'test-root-only' not in render_companion_html('test-root-only')
    for path in ['/', '/companion', '/companion/']:
        status, headers, html = request(path)
        assert status == 200
        if path == '/':
            assert '以 Google 登入' in html
            assert 'Node Map' not in html
        else:
            assert 'Node Map' in html
        assert 'test-root-only' not in html
        assert headers['X-Robots-Tag'] == 'noindex, nofollow'
        assert headers['Cache-Control'] == 'no-store'
        status, head_headers, body = request(path, method='HEAD')
        assert status == 200 and body == ''
        assert head_headers['Content-Length'] == headers['Content-Length']


def test_node_map_and_join_approval_require_root(gateway):
    request, fabric, store = gateway
    scoped = ClientTokenStore(store).issue('test-reader', label='reader', permissions=['project.read'], projects=['demo'])['token']
    join = fabric.request_join(manifest={'schema': 'agentos.node-manifest/v0.1', 'node_id': 'test-node', 'role': 'client'})
    for token, expected in [(None, 401), ('invalid', 403), (scoped, 403)]:
        assert request('/v1/nodes', token)[0] == expected
        assert request('/v1/nodes/approve', token, {'code': join['user_code']})[0] == expected
    assert fabric.join_status(request_id=join['request_id'], claim_secret=join['claim_secret'])['status'] == 'pending'
    status, _, body = request('/v1/nodes', 'test-root-only')
    assert status == 200 and json.loads(body)['schema'] == 'agentos.node-map/v0.1'
    assert request('/v1/nodes/approve', 'test-root-only', {})[0] == 400
    assert request('/v1/nodes/approve', 'test-root-only', {'code': 'nonexistent'})[0] == 400
    status, _, body = request('/v1/nodes/approve', 'test-root-only', {'code': join['user_code'].lower()})
    assert status == 200 and json.loads(body)['success'] is True
    assert fabric.join_status(request_id=join['request_id'], claim_secret=join['claim_secret'])['status'] == 'approved'


def test_client_tokens_are_hashed_scoped_and_revocable(gateway):
    _, _, store = gateway
    tokens = ClientTokenStore(store)
    issued = tokens.issue('reader', label='test', permissions=['project.read'], projects=['demo'], capabilities=['read'])
    token = issued['token']
    principal = tokens.principal(token)
    assert principal.allows_project('demo') and not principal.allows_project('other')
    assert not principal.allows_permission('task.submit')
    with store._connect() as connection:
        assert token not in str([dict(row) for row in connection.execute('SELECT * FROM client_tokens')])
    assert tokens.revoke(token)
    assert tokens.principal(token) is None
