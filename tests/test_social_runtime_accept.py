import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'social_runtime_accept.py'
spec = importlib.util.spec_from_file_location('social_runtime_accept', MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


class _Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode('utf-8')
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, _limit=-1):
        return self.payload


class SocialRuntimeAcceptanceCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = Path(self.temp.name) / 'social-runtime.env'
        self.env.write_text('AGENTOS_SOCIAL_CONTROL_TOKEN=private-control-value\n', encoding='utf-8')
        self.payload = {
            'schema': 'agentos.social-request/v1',
            'product_id': 'leopardcat-tarot',
            'platform': 'threads',
            'operation': 'publish',
            'account_binding_id': 'binding-1',
            'target_account_id': 'account-1',
            'primary_text': 'bounded primary text',
            'text_attachment': {'plaintext': 'long interpretation'},
            'write_intent_id': 'intent-1',
        }

    def tearDown(self):
        self.temp.cleanup()

    def test_load_control_token_requires_exact_single_nonempty_value(self):
        self.assertEqual(module._load_control_token(self.env), 'private-control-value')
        self.env.write_text('AGENTOS_SOCIAL_CONTROL_TOKEN=\n', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'unconfigured'):
            module._load_control_token(self.env)
        self.env.write_text('AGENTOS_SOCIAL_CONTROL_TOKEN=a\nAGENTOS_SOCIAL_CONTROL_TOKEN=b\n', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'invalid'):
            module._load_control_token(self.env)

    def test_read_request_rejects_non_write(self):
        payload = dict(self.payload, operation='status')
        payload.pop('write_intent_id')
        with self.assertRaisesRegex(ValueError, 'write_operation_required'):
            module._read_request(io.StringIO(json.dumps(payload)))

    def test_issue_acceptance_is_fixed_local_and_output_is_bounded(self):
        returned = {
            'schema': 'agentos.social-write-acceptance/v1',
            'acceptance_id': 'acceptance-123',
            'one_shot': 'true',
        }
        captured = {}
        def fake_urlopen(req, timeout):
            captured['url'] = req.full_url
            captured['headers'] = dict(req.header_items())
            captured['body'] = req.data
            captured['timeout'] = timeout
            return _Response(returned)
        with mock.patch.object(module.urllib.request, 'urlopen', side_effect=fake_urlopen):
            result = module.issue_acceptance(self.payload, token='private-control-value', timeout=4)
        self.assertEqual(captured['url'], 'http://127.0.0.1:8771/internal/v1/social/acceptances')
        self.assertEqual(captured['timeout'], 4)
        self.assertEqual(json.loads(captured['body']), self.payload)
        self.assertEqual(result, returned)
        self.assertNotIn('private-control-value', json.dumps(result))
        self.assertNotIn('bounded primary text', json.dumps(result))
        self.assertNotIn('long interpretation', json.dumps(result))

    def test_unexpected_runtime_field_rejected(self):
        returned = {
            'schema': 'agentos.social-write-acceptance/v1',
            'acceptance_id': 'acceptance-123',
            'one_shot': 'true',
            'access_token': 'must-not-pass',
        }
        with mock.patch.object(module.urllib.request, 'urlopen', return_value=_Response(returned)):
            with self.assertRaisesRegex(RuntimeError, 'unexpected_field'):
                module.issue_acceptance(self.payload, token='private-control-value')

    def test_oversized_stdin_rejected(self):
        with self.assertRaisesRegex(ValueError, 'request_size_invalid'):
            module._read_request(io.StringIO('x' * (module.MAX_STDIN_BYTES + 1)))


if __name__ == '__main__':
    unittest.main()
